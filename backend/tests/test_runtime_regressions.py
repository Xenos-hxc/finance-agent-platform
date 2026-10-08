"""Runtime regressions: real Redis/Chroma plus deterministic LLM faults.

Set FINANCE_AGENT_TEST_REDIS=true to include the local Redis integration tests.
Only this test's UUID-prefixed keys are removed; no FLUSHDB/FLUSHALL.
"""
import asyncio
import json
import os
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import chromadb
import pytest
import pytest_asyncio
import redis.asyncio as redis
import httpx
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

import api.main as api
from core.skill_loader import SkillManager
from core.llm_utils import create_message
from core.intent_recognizer import IntentRecognizer
from evaluation.evaluator import LLMJudge
from memory.conversation_memory import MemoryManager, MsgRole
from mcp.tool_manager import MCPToolManager, Tool, CircuitBreaker, CircuitState
from monitor.performance_monitor import PerformanceMonitor, Alert, Severity


def response(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture
def client(monkeypatch):
    kb = SimpleNamespace(add_documents_async=AsyncMock(return_value=1), doc_count_async=AsyncMock(return_value=2))
    manager = SimpleNamespace(_tools={"knowledge_search": SimpleNamespace(handler=SimpleNamespace(__self__=kb))},
                              invalidate_cache=Mock())
    monkeypatch.setattr(api, "_tool_manager", manager)
    return TestClient(api.app)


@pytest.mark.parametrize("payload", [b"{", b"{}", b"[]", b"null", b"[1]", b'[{"title":"x","content":" "}]'])
def test_invalid_uploads(client, payload):
    assert client.post("/knowledge/upload", files={"file": ("bad.json", payload)}).status_code == 400


@pytest.mark.parametrize("filename,payload,status", [("bad.pdf", b"%PDF", 415), ("empty.txt", b"", 400),
    ("invalid.txt", b"\xff", 400), ("ok.TXT", "服务说明".encode(), 200)])
def test_upload_formats(client, filename, payload, status):
    assert client.post("/knowledge/upload", files={"file": (filename, payload)}).status_code == status


@pytest.mark.parametrize("path,body", [("/chat", {"message":" "}), ("/chat", {}),
    ("/knowledge/add", {"documents":[]}), ("/knowledge/add", {"documents":[{"title":"x","content":" "}]}),
    ("/eval/run", {"dialog_cases":[{}]}), ("/eval/run", {"dialog_cases":[{"turns":[""]}]})])
def test_empty_requests(client, path, body):
    assert client.post(path, json=body).status_code == 422


@pytest.mark.parametrize("query,k", [("",1), ("  ",1), ("query",0), ("query",-1), ("query",51)])
def test_search_validation(client, query, k):
    assert client.post("/search", params={"query":query,"top_k":k}).status_code == 422


@pytest_asyncio.fixture
async def manager():
    value = MCPToolManager(api_key="test-local-only")
    yield value
    await value._client.close()


@pytest.mark.asyncio
async def test_cache_expiry_invalidation_and_unknown_tool(manager, monkeypatch):
    handler = AsyncMock(return_value=[{"content":"old"}])
    manager.register(Tool("test", "test", handler, {"required":["query"],"properties":{"query":{"type":"string"}}}, cache_ttl=300))
    assert not (await manager.call("missing", {})).success
    assert not (await manager.call("test", {})).success
    first = await manager.call("test", {"query":"same"})
    second = await manager.call("test", {"query":"same"})
    assert first.success and second.cached and handler.await_count == 1
    manager.invalidate_cache("test")
    handler.return_value = [{"content":"new"}]
    assert (await manager.call("test", {"query":"same"})).data[0]["content"] == "new"
    for key, (data, _, reranked) in list(manager._cache.items()):
        manager._cache[key] = (data, 0, reranked)
    assert not (await manager.call("test", {"query":"same"})).cached
    manager.unregister("test")
    assert not (await manager.call("test", {})).success


@pytest.mark.asyncio
async def test_timeout_fallback_and_breaker(manager):
    async def slow(params, context):
        await asyncio.sleep(1)
    tool = Tool("slow", "test", slow, {}, timeout_s=0.001, fallback=lambda *args: {"fallback":True})
    tool.breaker = CircuitBreaker(1, 60)
    manager.register(tool)
    result = await manager.call("slow", {})
    assert result.error and result.data["fallback"]
    assert tool.breaker.state == CircuitState.OPEN
    assert (await manager.call("slow", {})).error
    tool.breaker.opened_at -= 61
    assert tool.breaker.allow()
    assert not tool.breaker.allow()
    tool.breaker.record_success()
    assert tool.breaker.allow()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["[0,0]", "[true,1]", "[-1,0]", "[99]", "[]", "not json"])
async def test_bad_reranking_is_truthfully_marked(manager, text):
    manager._client.messages.create = AsyncMock(return_value=response(text))
    items = [{"id":str(i),"content":str(i)} for i in range(3)]
    ranked, applied = await manager._rerank_with_status("q", items, 2)
    assert ranked == items[:2] and not applied


@pytest.mark.asyncio
async def test_valid_partial_ranking_fills_remaining(manager):
    manager._client.messages.create = AsyncMock(return_value=response("[2]"))
    ranked, applied = await manager._rerank_with_status("q", [0,1,2], 2)
    assert ranked == [2,0] and applied


@pytest.mark.asyncio
async def test_rewrite_bounds_dedup_and_score_independent_merge(manager):
    manager._client.messages.create = AsyncMock(return_value=response('["other", "", 2, "other", "third", "fourth"]'))
    queries = await manager.rewrite_query("original", n=3)
    assert queries[0] == "original" and len(queries) <= 4 and all(isinstance(x,str) for x in queries)
    async def search(params, context):
        return [{"title":"same","content":"same","score":0.1 if params['query']=='original' else 0.9}]
    manager.register(Tool("search", "", search, {}))
    result = await manager.search_with_rewrite("search", "original", 5)
    assert result.success and len(result.data) == 1 and not result.reranked


class TinyEmbedding:
    def __call__(self, input):
        return [[1.0, 0.0, 0.0] for _ in input]


@pytest_asyncio.fixture
async def memory(tmp_path):
    if os.getenv("FINANCE_AGENT_TEST_REDIS") != "true":
        pytest.skip("set FINANCE_AGENT_TEST_REDIS=true for local integration")
    value = MemoryManager.__new__(MemoryManager)
    value._redis = redis.from_url("redis://127.0.0.1:6379/13", decode_responses=True)
    value._model = "test"
    value._client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response("设备编号 LQ739188，需要保修。"))))
    chroma = chromadb.PersistentClient(path=str(tmp_path / "chroma"), settings=chromadb.Settings(anonymized_telemetry=False))
    value._episodic = chroma.get_or_create_collection("episodic", embedding_function=TinyEmbedding())
    value._profile = chroma.get_or_create_collection("user_profile", embedding_function=TinyEmbedding())
    value.test_user = "regression-" + uuid4().hex
    yield value
    await value._redis.delete(value._wm_key(value.test_user,"c"), value._summary_key(value.test_user,"c"))
    await value.close()


async def seed(memory, count):
    for i in range(count):
        await memory.add_message(memory.test_user,"c",MsgRole.USER,f"message-{i}")


@pytest.mark.asyncio
async def test_real_redis_compression_order_and_chroma_filter(memory):
    await seed(memory,15)
    context = await memory.get_context(memory.test_user,"c","设备")
    assert [m.content for m in context.recent_messages] == [f"message-{i}" for i in range(10,15)]
    assert "LQ739188" in context.summary and context.relevant_history
    assert (await memory.get_context(memory.test_user,"another","设备")).relevant_history
    assert not (await memory.get_context(memory.test_user+"-other","c","设备")).relevant_history


@pytest.mark.asyncio
async def test_summary_failure_keeps_all_messages(memory):
    memory._client.messages.create.side_effect = RuntimeError("model unavailable")
    await seed(memory,15)
    assert len(await memory._get_working_memory(memory.test_user,"c")) == 15
    assert memory._episodic.count() == 0


@pytest.mark.asyncio
async def test_concurrent_append_during_summary_is_preserved(memory):
    async def summarize(**kwargs):
        await memory._redis.lpush(memory._wm_key(memory.test_user,"c"), json.dumps({"role":"user","content":"concurrent","ts":"2026-10-04T00:00:00"}))
        return response("有效摘要")
    memory._client.messages.create.side_effect = summarize
    await seed(memory,15)
    messages = await memory._get_working_memory(memory.test_user,"c")
    assert [m.content for m in messages] == [f"message-{i}" for i in range(10,15)] + ["concurrent"]


@pytest.mark.asyncio
async def test_profile_upsert_is_unique(memory):
    await seed(memory,2)
    memory._client.messages.create.return_value = response('{"preferences":["中文"],"entities":{}}')
    await memory.update_profile(memory.test_user,"c")
    await memory.update_profile(memory.test_user,"c")
    assert memory._profile.count() == 1
    assert (await memory._get_profile(memory.test_user))["preferences"] == ["中文"]


def test_skill_hot_reload_and_bad_file_isolation(tmp_path):
    path=tmp_path / "test.json"
    path.write_text(json.dumps({"name":"退款","content":"流程 A","agents":["billing"],"keywords":["退款"]}),encoding="utf8")
    (tmp_path / "bad.json").write_text("{bad",encoding="utf8")
    skills=SkillManager(str(tmp_path))
    skills.load()
    assert len(skills.skills)==1 and len(skills.errors)==1
    assert skills.skills[0].matches("申请退款","billing")
    assert not skills.skills[0].matches("申请退款","technical")
    path.write_text(json.dumps({"name":"退款","content":"流程 B"}),encoding="utf8")
    skills.load()
    assert skills.skills[0].content == "流程 B"


@pytest.mark.asyncio
async def test_monitor_metrics_alert_resolution_and_feedback():
    orchestrator = Mock()
    orchestrator.get_stats.return_value = {"technical":{"success_rate":0.5,"avg_ms":4000,"total":12,"routing_score":0.2}}
    tools = Mock()
    tools.get_stats.return_value = {}
    monitor = PerformanceMonitor(orchestrator,tools)
    await monitor._collect()
    await monitor._collect()
    assert len(monitor.summary()["active_alerts"])==2
    assert monitor.summary()["suggestions"]
    assert orchestrator.update_routing_penalties.call_args.args[0]["technical"]>0
    metrics=generate_latest(monitor.registry).decode()
    assert "requests_total 12.0" in metrics and "agent_latency_ms" in metrics
    orchestrator.get_stats.return_value["technical"].update(success_rate=1.0,avg_ms=100)
    await monitor._collect()
    assert not monitor.summary()["active_alerts"]


@pytest.mark.asyncio
async def test_judge_failure_is_marked():
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("model down"))))
    scores=await LLMJudge(client,"test").judge("q","a")
    assert scores.judge_failed and scores.error and scores.overall==0.5


@pytest.mark.asyncio
@pytest.mark.parametrize("base_url,disabled", [("https://api.deepseek.com/anthropic",True),
    ("https://api.anthropic.com",False),("https://api.deepseek.com.example.invalid",False)])
async def test_provider_options_only_apply_to_deepseek(base_url,disabled):
    client=SimpleNamespace(base_url=base_url,messages=SimpleNamespace(create=AsyncMock(return_value=response("ok"))))
    await create_message(client,model="test",max_tokens=256,messages=[])
    kwargs=client.messages.create.call_args.kwargs
    assert (kwargs.get("extra_body",{}).get("thinking")=={"type":"disabled"}) == disabled


@pytest.mark.asyncio
async def test_few_shot_examples_actually_reach_model():
    recognizer=IntentRecognizer(api_key="test-local-only")
    recognizer.client.messages.create=AsyncMock(return_value=response('{"intent":"request","confidence":0.95}'))
    await recognizer._llm_recognize("修改收货地址",None)
    prompt=recognizer.client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "我需要修改地址" in prompt and "消息:" in prompt and "示例:" in prompt
    await recognizer.client.close()


@pytest.mark.asyncio
async def test_two_compressions_cannot_remove_messages_twice(memory):
    memory.COMPRESS_AT=100
    await seed(memory,15)
    memory.COMPRESS_AT=15
    barrier=asyncio.Event()
    calls=0
    async def summarize(**kwargs):
        nonlocal calls
        calls += 1
        if calls==2: barrier.set()
        await asyncio.wait_for(barrier.wait(),timeout=3)
        return response("同一批消息的摘要")
    memory._client.messages.create.side_effect=summarize
    await asyncio.gather(memory._compress(memory.test_user,"c"),memory._compress(memory.test_user,"c"))
    assert [m.content for m in await memory._get_working_memory(memory.test_user,"c")] == [f"message-{i}" for i in range(10,15)]
    assert memory._episodic.count()==1


@pytest.mark.asyncio
async def test_webhook_payload_has_serializable_severity(monkeypatch):
    received=[]
    def receive(request):
        received.append(json.loads(request.content))
        return httpx.Response(200,json={"ok":True})
    client=httpx.AsyncClient(transport=httpx.MockTransport(receive))
    monkeypatch.setattr("monitor.performance_monitor.httpx.AsyncClient",lambda **kwargs:client)
    monitor=PerformanceMonitor(Mock(),Mock(),webhook_url="http://localhost/test-webhook")
    await monitor._send_webhook(Alert(Severity.WARNING,"test","local test",1,0))
    assert received[0]["severity"]=="warning"

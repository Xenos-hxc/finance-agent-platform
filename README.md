# 金融理财客服平台多Agent协作系统

[![CI](https://github.com/Xenos-hxc/finance-agent-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Xenos-hxc/finance-agent-platform/actions/workflows/ci.yml)

面向金融理财客服场景的多 Agent 协作平台，基于 FastAPI 与 Vue 3，整合意图识别、Agent 路由、知识库检索、工具调用、分层记忆、评测和运行监控。

## 架构与目录

| 目录 | 职责 |
| --- | --- |
| `backend/api/` | FastAPI 对话、知识库、监控和评测接口 |
| `backend/agents/` | Agent 编排、回答组合与工具调用 |
| `backend/core/` | 意图识别、模型调用与业务规则加载 |
| `backend/mcp/` | 知识库检索和工具管理 |
| `backend/memory/` | Redis 短期记忆与 ChromaDB 长期记忆 |
| `backend/skills/` | 各类客服任务的业务规则 |
| `backend/evaluation/`、`backend/monitor/` | 回归评测、质量统计与性能监控 |
| `frontend/` | Vue 3 对话、知识库与评测工作台 |

请求经过记忆读取、意图识别、Agent 路由、知识检索和工具调用，生成回复后写回记忆。业务规则通过 Skills 文件维护，评测报告用于观察路由效果和回答质量。

## Docker 启动

需要 Docker 和 Docker Compose。复制根目录 `.env.example` 为 `.env`，填写模型 API Key，并设置 Redis 密码。

```bash
cp .env.example .env
docker compose --env-file .env -f frontend/docker-compose.yml up -d --build
```

Windows 可用 `Copy-Item .env.example .env`。前端入口为 `http://localhost:5174`，统一网关为 `http://localhost`，后端 API 文档为 `http://localhost:8000/docs`。

首次构建后端镜像会下载 Python 依赖与 embedding 模型，需要网络连接。真实模型回复需要有效的模型服务配置；会话记录、用户画像、知识库和评测基线由运行时生成。

## 本地开发

后端需要 Python 3.11 或 3.12，以及 Redis。在 `backend/` 目录执行：

```bash
python -m venv .venv
# 激活虚拟环境后执行
pip install -r requirements-dev.txt
cp .env.example .env
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

前端需要 Node.js 22.12+，在 `frontend/` 目录执行：

```bash
npm ci
npm run dev
```

访问 `http://localhost:5173`。开发代理将 `/api` 请求转发到 `http://localhost:8000`；可通过 `VITE_API_TARGET` 设置其他代理目标。前端生产 API 地址可通过 `VITE_API_URL` 或 Docker 运行时的 `API_URL` 设置。

## 配置

模型连接使用 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL`。Redis 使用 `REDIS_URL`。ChromaDB 数据目录使用 `CHROMA_PERSIST_DIRECTORY`，业务规则目录使用 `FINANCE_AGENT_SKILLS_DIR`。

Agent 与回答组合配置统一使用 `FINANCE_AGENT_` 环境变量前缀，包括 `FINANCE_AGENT_COMPOSER_MAX_TOKENS`、`FINANCE_AGENT_COMPOSER_TEMPERATURE` 及各 Agent 的模型设置。

## 验证

- 后端：在 `backend/` 中执行 `python -m pytest tests`。
- 前端：在 `frontend/` 中执行 `npm run build`。
- Redis 集成测试：设置 `FINANCE_AGENT_TEST_REDIS=true`，并使用隔离的测试 Redis 服务。

GitHub Actions 自动检查 Python 回归测试和前端生产构建。`.env`、密钥、会话数据、导入知识库和构建产物均被 Git 忽略。示例密码仅供本地演示；公网部署需配置身份认证、访问控制和 HTTPS。

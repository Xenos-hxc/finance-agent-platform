"""LLM response helpers shared by Anthropic-compatible providers."""
import os
from typing import Any, Iterable, List
from urllib.parse import urlsplit


async def create_message(client: Any, **kwargs: Any) -> Any:
    """Keep short JSON/tool requests compatible with DeepSeek's default thinking mode.

    DeepSeek enables thinking by default. A 256-token budget can be exhausted
    before any text block is produced. Disable it explicitly for this provider;
    other Anthropic-compatible endpoints keep their existing request format.
    https://api-docs.deepseek.com/guides/thinking_mode/
    """
    host = urlsplit(str(getattr(client, "base_url", ""))).hostname
    if host == "api.deepseek.com":
        mode = os.getenv("ECHOMIND_DEEPSEEK_THINKING", "disabled").lower()
        if mode in {"disabled", "enabled"}:
            body = dict(kwargs.get("extra_body") or {})
            body.setdefault("thinking", {"type": mode})
            kwargs["extra_body"] = body
    return await client.messages.create(**kwargs)


def extract_text_content(content: Iterable[Any]) -> str:
    """Return text blocks from Anthropic-style response content."""
    texts: List[str] = []
    for block in content or []:
        if isinstance(block, str):
            texts.append(block)
            continue

        block_type = getattr(block, "type", None)
        text = getattr(block, "text", None)
        if isinstance(block, dict):
            block_type = block.get("type", block_type)
            text = block.get("text", text)

        if isinstance(text, str) and (block_type in (None, "text")):
            texts.append(text)

    return "\n".join(t for t in texts if t)

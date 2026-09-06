from __future__ import annotations

import json
from typing import Any, Literal

from app.config import get_settings
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from worker.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResult,
    ToolCall,
    ToolSpec,
    Usage,
)

_TOOL_CHOICE = {
    "auto": {"type": "auto"},
    "any": {"type": "any"},
    "none": {"type": "none"},
}


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, LLMError) and exc.retryable


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMError("anthropic SDK not installed", kind="config") from exc
        key = api_key or get_settings().anthropic_api_key
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set", kind="config")
        self._client = AsyncAnthropic(api_key=key, timeout=120.0, max_retries=0)

    @staticmethod
    def _to_anthropic_messages(messages: list[LLMMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool_result":
                out.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id or "",
                                "content": m.content,
                            }
                        ],
                    }
                )
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append(
                        {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                    )
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    @retry(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[LLMMessage],
        tools: list[ToolSpec] | None = None,
        tool_choice: str | Literal["auto", "any", "none"] = "auto",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": self._to_anthropic_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters}
                for t in tools
            ]
            kwargs["tool_choice"] = _TOOL_CHOICE.get(tool_choice, {"type": "auto"})

        try:
            resp = await self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status_code", None)
            retryable = status in (408, 429, 500, 502, 503, 529) if status else True
            raise LLMError(f"Anthropic call failed: {exc}", retryable=retryable) from exc

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                args = (
                    block.input
                    if isinstance(block.input, dict)
                    else json.loads(block.input or "{}")
                )
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=args))

        return LLMResult(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=Usage(resp.usage.input_tokens, resp.usage.output_tokens),
            stop_reason=resp.stop_reason or "end_turn",
            model=model,
            raw=resp,
        )

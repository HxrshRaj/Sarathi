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
from worker.llm.schema_gemini import to_gemini_schema

_MODE = {"auto": "AUTO", "any": "ANY", "none": "NONE"}
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def _retryable(exc: BaseException) -> bool:
    return isinstance(exc, LLMError) and exc.retryable


class GeminiProvider(LLMProvider):
    """Google Gemini via the `google-genai` SDK. Function-calling backs
    `structured()` and the agent tool loop; system prompt -> system_instruction.
    """

    name = "gemini"

    def __init__(self, api_key: str | None = None) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover
            raise LLMError("google-genai SDK not installed", kind="config") from exc
        key = api_key or get_settings().gemini_api_key
        if not key:
            raise LLMError("GEMINI_API_KEY is not set", kind="config")
        self._genai = genai
        self._client = genai.Client(api_key=key)

    # ── message mapping ────────────────────────────────────────────────────
    def _to_contents(self, messages: list[LLMMessage]) -> list[Any]:
        types = self._genai.types
        id_to_name: dict[str, str] = {}
        for m in messages:
            for tc in m.tool_calls:
                id_to_name[tc.id] = tc.name

        contents: list[Any] = []
        for m in messages:
            if m.role == "tool_result":
                name = id_to_name.get(m.tool_call_id or "", "tool")
                try:
                    payload = json.loads(m.content)
                except (TypeError, ValueError):
                    payload = {"result": m.content}
                if not isinstance(payload, dict):
                    payload = {"result": payload}
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=name, response=payload
                                )
                            )
                        ],
                    )
                )
            elif m.role == "assistant" and m.tool_calls:
                parts = []
                if m.content:
                    parts.append(types.Part(text=m.content))
                for tc in m.tool_calls:
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(name=tc.name, args=tc.arguments)
                        )
                    )
                contents.append(types.Content(role="model", parts=parts))
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=m.content or "")]))
        return contents

    def _tools(self, specs: list[ToolSpec] | None) -> list[Any] | None:
        if not specs:
            return None
        types = self._genai.types
        decls = [
            types.FunctionDeclaration(
                name=s.name,
                description=s.description,
                parameters=to_gemini_schema(s.parameters),
            )
            for s in specs
        ]
        return [types.Tool(function_declarations=decls)]

    @retry(
        retry=retry_if_exception(_retryable),
        stop=stop_after_attempt(5),
        # free-tier 429s ask for ~20-30s backoff
        wait=wait_exponential(multiplier=2, min=2, max=45),
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
        types = self._genai.types
        cfg_kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        gem_tools = self._tools(tools)
        if gem_tools:
            cfg_kwargs["tools"] = gem_tools
            cfg_kwargs["tool_config"] = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=_MODE.get(tool_choice, "AUTO")
                )
            )

        try:
            resp = await self._client.aio.models.generate_content(
                model=model,
                contents=self._to_contents(messages),
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            raise LLMError(
                f"Gemini call failed: {exc}",
                retryable=(status in _RETRY_STATUS) if isinstance(status, int) else True,
            ) from exc

        candidates = getattr(resp, "candidates", None) or []
        if not candidates:
            reason = getattr(getattr(resp, "prompt_feedback", None), "block_reason", "unknown")
            raise LLMError(f"Gemini returned no candidates (block_reason={reason})", kind="model")

        parts = getattr(candidates[0].content, "parts", None) or []
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for i, part in enumerate(parts):
            if getattr(part, "text", None):
                text_parts.append(part.text)
            fc = getattr(part, "function_call", None)
            if fc is not None:
                args = dict(fc.args) if fc.args else {}
                tool_calls.append(ToolCall(id=f"call_{i}_{fc.name}", name=fc.name, arguments=args))

        um = getattr(resp, "usage_metadata", None)
        usage = Usage(
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
        )
        finish = str(getattr(candidates[0], "finish_reason", "") or "")
        return LLMResult(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage=usage,
            stop_reason="tool_use" if tool_calls else (finish or "stop"),
            model=model,
            raw=resp,
        )

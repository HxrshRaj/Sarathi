"""Deterministic offline stand-in for a real provider.

Purpose: let the stack boot, tests run, and the pipeline be demoed with NO API
key. It is a test double, clearly labelled — it does not pretend to reason. When
`LLM_PROVIDER=anthropic` and a key is present, this class is never used.

Behaviour:
- `structured()` path: synthesise a schema-valid minimal instance of the output
  model, echoing task text into obvious string fields where it helps a demo read.
- agentic `complete()` with tools: return a short "no further action" turn so
  loops terminate deterministically.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from worker.llm.base import LLMMessage, LLMProvider, LLMResult, ToolCall, ToolSpec, Usage


def _seed(messages: list[LLMMessage]) -> str:
    joined = "\n".join(m.content for m in messages)[:4000]
    return hashlib.sha256(joined.encode()).hexdigest()[:8]


def _minimal_for_schema(schema: dict[str, Any], defs: dict[str, Any], hint: str) -> Any:
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        return _minimal_for_schema(defs.get(ref, {}), defs, hint)
    if "anyOf" in schema or "oneOf" in schema:
        options = schema.get("anyOf") or schema.get("oneOf")
        non_null = [o for o in options if o.get("type") != "null"]
        return _minimal_for_schema((non_null or options)[0], defs, hint)
    if "enum" in schema:
        return schema["enum"][0]

    t = schema.get("type")
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        required = set(schema.get("required", props.keys()))
        return {k: _minimal_for_schema(v, defs, hint) for k, v in props.items() if k in required}
    if t == "array":
        item_schema = schema.get("items", {"type": "string"})
        return [_minimal_for_schema(item_schema, defs, hint)] if schema.get("minItems", 0) else []
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    if t == "string":
        fmt = schema.get("format")
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if fmt in ("date-time", "date"):
            return "2026-01-01T00:00:00Z"
        return hint[:200]
    return None


class FakeProvider(LLMProvider):
    name = "fake"

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
        usage = Usage(input_tokens=200, output_tokens=120)
        hint = f"[fake-llm {_seed(messages)}] " + (messages[-1].content[:160] if messages else "")

        if tools and tool_choice in ("any",):
            spec = tools[0]
            defs = spec.parameters.get("$defs", {}) or spec.parameters.get("definitions", {})
            args = _minimal_for_schema(spec.parameters, defs, hint)
            return LLMResult(
                text="",
                tool_calls=[ToolCall(id="fake_call_1", name=spec.name, arguments=args or {})],
                usage=usage,
                stop_reason="tool_use",
                model="fake",
            )

        # agentic loop: no tool call -> caller treats as "finished"
        return LLMResult(
            text="FAKE_LLM: no external key configured; returning no-op turn.",
            tool_calls=[],
            usage=usage,
            stop_reason="end_turn",
            model="fake",
        )

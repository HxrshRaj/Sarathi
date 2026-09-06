"""Provider-agnostic LLM interface.

The rest of the runtime depends only on this module — never on a vendor SDK.
Adding a provider = one subclass of `LLMProvider`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

Role = Literal["user", "assistant", "tool_result"]


class LLMError(Exception):
    """Raised for transport failures, refusals, or unrecoverable invalid output."""

    def __init__(self, message: str, *, retryable: bool = False, kind: str = "model") -> None:
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (object)

    @classmethod
    def from_model(cls, name: str, description: str, model: type[BaseModel]) -> ToolSpec:
        schema = model.model_json_schema()
        schema.pop("title", None)
        return cls(name=name, description=description, parameters=schema)


@dataclass(slots=True)
class LLMMessage:
    role: Role
    content: str
    # for role="tool_result"
    tool_call_id: str | None = None
    # for role="assistant" replay of a prior tool call
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    # opaque per-provider round-trip state (e.g. Gemini 3.x `thought_signature`)
    provider_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResult:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop_reason: str
    model: str
    raw: Any = None

    def first_tool(self, name: str | None = None) -> ToolCall | None:
        for tc in self.tool_calls:
            if name is None or tc.name == name:
                return tc
        return None


T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """One completion call. Retries/timeouts are the implementation's concern."""

    name: str = "base"

    @abstractmethod
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
    ) -> LLMResult: ...

    async def structured(
        self,
        *,
        model: str,
        system: str,
        messages: list[LLMMessage],
        output_model: type[T],
        tool_name: str = "emit_result",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        repair_attempts: int = 1,
    ) -> tuple[T, Usage]:
        """Force a single tool whose args are `output_model`; validate → repair → fail."""
        spec = ToolSpec.from_model(
            tool_name, f"Return the result as {output_model.__name__}.", output_model
        )
        convo = list(messages)
        total = Usage()

        for attempt in range(repair_attempts + 1):
            result = await self.complete(
                model=model,
                system=system,
                messages=convo,
                tools=[spec],
                tool_choice="any",
                max_tokens=max_tokens,
                temperature=temperature,
            )
            total = total + result.usage
            call = result.first_tool(tool_name) or result.first_tool()
            if call is None:
                convo.append(LLMMessage(role="user", content="You must call the tool. Try again."))
                continue
            try:
                return output_model.model_validate(call.arguments), total
            except ValidationError as exc:
                if attempt >= repair_attempts:
                    raise LLMError(
                        f"Invalid structured output for {output_model.__name__}: {exc.errors()[:3]}",
                        kind="model_invalid_output",
                    ) from exc
                convo.append(
                    LLMMessage(
                        role="user",
                        content=(
                            "Your previous tool call failed schema validation with:\n"
                            f"{json.dumps(exc.errors()[:5], default=str)}\n"
                            "Call the tool again with corrected arguments."
                        ),
                    )
                )
        raise LLMError("structured() exhausted attempts", kind="model_invalid_output")

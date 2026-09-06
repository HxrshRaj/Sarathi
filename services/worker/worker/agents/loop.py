"""Shared tool-using loop for agents that act on the workspace.

Runs completion turns until the model stops calling tools or a cap is hit. Every
tool call is validated by the registry and recorded. Budget + cancellation are
checked each turn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.models.run import ToolCall as ToolCallRow

from worker.agents.base import AgentError
from worker.llm.base import LLMMessage, ToolCall
from worker.prompts import get_prompt
from worker.runtime.context import RunContext
from worker.tools.base import ToolRegistry

_MAX_TURNS = 24
_MAX_RESULT_CHARS = 12000


@dataclass(slots=True)
class LoopOutcome:
    final_text: str
    turns: int
    tool_calls: int
    tool_failures: int


async def run_tool_loop(
    ctx: RunContext,
    *,
    prompt_name: str,
    registry: ToolRegistry,
    tool_names: list[str],
    user_message: str,
    max_turns: int = _MAX_TURNS,
    agent_label: str = "coder",
    step_seq: int = 0,
) -> LoopOutcome:
    prompt = get_prompt(prompt_name)
    system = prompt.render_system()
    specs = registry.specs(tool_names)
    messages: list[LLMMessage] = [LLMMessage(role="user", content=user_message)]

    tool_calls = tool_failures = 0
    seq = 0
    turns = 0

    for turn_index in range(max_turns):
        turns = turn_index + 1
        ctx.budget.check()
        if ctx.emitter.cancelled():
            raise AgentError("cancelled", category="cancelled")
        ctx.budget.tick_iteration()

        result = await ctx.llm.complete(
            model=ctx.model,
            system=system,
            messages=messages,
            tools=specs,
            tool_choice="auto",
            max_tokens=prompt.model_config.get("max_tokens", 8000),
            temperature=prompt.model_config.get("temperature", 0.0),
        )
        ctx.budget.add_usage(result.usage)

        if not result.tool_calls:
            return LoopOutcome(result.text.strip(), turns, tool_calls, tool_failures)

        messages.append(
            LLMMessage(role="assistant", content=result.text, tool_calls=result.tool_calls)
        )
        for call in result.tool_calls:
            seq += 1
            tool_calls += 1
            tr = registry.invoke(call.name, call.arguments)
            if not tr.ok:
                tool_failures += 1
            ctx.db.add(
                ToolCallRow(
                    agent_step_id=ctx._current_step_id,
                    seq=seq,
                    tool=call.name,
                    args_json=_safe(call.arguments),
                    result_json=_safe(tr.data),
                    ok=tr.ok,
                    error=tr.error,
                    duration_ms=tr.duration_ms,
                )
            )
            ctx.db.flush()
            ctx.emitter.emit(
                "tool.result",
                {
                    "tool": call.name,
                    "ok": tr.ok,
                    "error": tr.error,
                    "summary": _summarize(call, tr),
                },
                agent=agent_label,
                step_seq=step_seq,
            )
            messages.append(
                LLMMessage(
                    role="tool_result",
                    tool_call_id=call.id,
                    content=json.dumps(
                        {"ok": tr.ok, "error": tr.error, "data": tr.data}, default=str
                    )[:_MAX_RESULT_CHARS],
                )
            )

    raise AgentError(
        f"{agent_label} exceeded {max_turns} turns without finishing", category="agent"
    )


def _safe(obj: dict | None) -> dict:
    if not obj:
        return {}
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError):
        return {"_unserializable": True}


def _summarize(call: ToolCall, tr) -> str:  # noqa: ANN001
    if call.name in ("create_file", "edit_file", "delete_file") and tr.ok:
        ch = tr.data.get("change", {})
        return f"{ch.get('change_type')} {ch.get('path')} (+{ch.get('lines_added',0)}/-{ch.get('lines_removed',0)})"
    if call.name == "run_tests":
        return f"exit {tr.data.get('exit_code')} · {tr.data.get('passed',0)}P/{tr.data.get('failed',0)}F"
    return "ok" if tr.ok else (tr.error or "error")

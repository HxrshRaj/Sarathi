"""Tool contract + registry + the workspace path jail.

Every tool the agent can call is registered here with a JSON-schema for its args.
There is deliberately no `run_shell` / `exec` / network tool. Execution tools
delegate to the sandbox. Path args are jailed to the run workspace.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from worker.llm.base import ToolSpec


class ToolError(Exception):
    def __init__(self, message: str, *, kind: str = "tool") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(slots=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0


# ── path jail ──────────────────────────────────────────────────────────────────
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def resolve_in_workspace(workspace: Path, rel_path: str) -> Path:
    """Resolve `rel_path` under `workspace`, rejecting any escape.

    Blocks: absolute paths, `..` traversal, NUL bytes, symlinks that resolve
    outside the workspace, and Windows reserved device names.
    """
    if not rel_path or "\x00" in rel_path:
        raise ToolError("Invalid path", kind="path_jail")
    candidate = Path(rel_path)
    if candidate.is_absolute() or candidate.drive or rel_path.startswith(("/", "\\")):
        raise ToolError(f"Absolute paths are not allowed: {rel_path!r}", kind="path_jail")
    parts = [p for p in candidate.parts if p not in (".",)]
    if any(p == ".." for p in parts):
        raise ToolError(f"Path traversal is not allowed: {rel_path!r}", kind="path_jail")
    if any(Path(p).stem.lower() in _WINDOWS_RESERVED for p in parts):
        raise ToolError(f"Reserved device name in path: {rel_path!r}", kind="path_jail")

    ws_root = workspace.resolve()
    target = (ws_root / candidate).resolve()
    try:
        target.relative_to(ws_root)
    except ValueError as exc:
        raise ToolError(f"Path escapes the workspace: {rel_path!r}", kind="path_jail") from exc

    # symlink component check: no existing component may be a symlink pointing out
    probe = ws_root
    for part in candidate.parts:
        probe = probe / part
        if probe.is_symlink():
            real = probe.resolve()
            try:
                real.relative_to(ws_root)
            except ValueError as exc:
                raise ToolError("Symlink escapes the workspace", kind="path_jail") from exc
    return target


# ── tool + registry ──────────────────────────────────────────────────────────
@dataclass(slots=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., ToolResult]
    mutating: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec.from_model(self.name, self.description, self.args_model)


class ToolRegistry:
    def __init__(self, *, allow_mutations: bool) -> None:
        self._tools: dict[str, Tool] = {}
        self._allow_mutations = allow_mutations
        self.calls: list[dict[str, Any]] = []

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for t in tools:
            self.register(t)

    def specs(self, names: list[str] | None = None) -> list[ToolSpec]:
        chosen = self._tools.values() if names is None else [self._tools[n] for n in names]
        return [t.spec() for t in chosen if not (t.mutating and not self._allow_mutations)]

    def has(self, name: str) -> bool:
        return name in self._tools

    def invoke(self, name: str, raw_args: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        tool = self._tools.get(name)
        if tool is None:
            res = ToolResult(ok=False, error=f"Unknown tool: {name}")
        elif tool.mutating and not self._allow_mutations:
            res = ToolResult(ok=False, error=f"Tool '{name}' is disabled at this autonomy level")
        else:
            try:
                args = tool.args_model.model_validate(raw_args)
            except ValidationError as exc:
                res = ToolResult(ok=False, error=f"Invalid arguments: {exc.errors()[:3]}")
            else:
                try:
                    res = tool.handler(args)
                except ToolError as exc:
                    res = ToolResult(ok=False, error=str(exc))
                except Exception as exc:  # noqa: BLE001 - tool bugs must not kill the run
                    res = ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")
        res.duration_ms = int((time.perf_counter() - started) * 1000)
        self.calls.append(
            {
                "tool": name,
                "args": raw_args,
                "ok": res.ok,
                "error": res.error,
                "duration_ms": res.duration_ms,
            }
        )
        return res

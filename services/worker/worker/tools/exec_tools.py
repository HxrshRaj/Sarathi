"""Execution tools. Every one runs inside the sandbox — never on the worker host.

If the sandbox is unavailable these return ok=False with reason "sandbox
unavailable"; callers must surface the step as *blocked*, not passed/failed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from worker.sandbox import SandboxConfig, SandboxError, SandboxResult, SandboxRunner
from worker.tools.base import Tool, ToolResult

_PYTEST_SUMMARY = re.compile(r"(\d+) passed|(\d+) failed|(\d+) error", re.I)


@dataclass(slots=True)
class ExecContext:
    workspace: Path
    language: str
    test_command: list[str] | None
    lint_command: list[str] | None
    format_command: list[str] | None
    runner: SandboxRunner | None


class NoArgs(BaseModel):
    pass


class RunTestsArgs(BaseModel):
    command: list[str] | None = Field(
        default=None, description="override argv, e.g. ['pytest','-q','tests/test_x.py']"
    )


class RunSecurityScanArgs(BaseModel):
    tools: list[str] = Field(default_factory=lambda: ["bandit", "pip_audit"])


def _parse_pytest(res: SandboxResult) -> dict:
    passed = failed = errors = 0
    for m in _PYTEST_SUMMARY.finditer(res.stdout + res.stderr):
        if m.group(1):
            passed = int(m.group(1))
        elif m.group(2):
            failed = int(m.group(2))
        elif m.group(3):
            errors = int(m.group(3))
    return {"passed": passed, "failed": failed, "errors": errors}


def build_exec_tools(ctx: ExecContext) -> list[Tool]:
    def _run(command: list[str], timeout_s: int | None = None) -> ToolResult:
        if ctx.runner is None:
            return ToolResult(ok=False, error="sandbox unavailable", data={"blocked": True})
        try:
            res = ctx.runner.run(
                workspace_dir=ctx.workspace,
                command=command,
                language=ctx.language,
                timeout_s=timeout_s,
            )
        except SandboxError as exc:
            return ToolResult(ok=False, error=f"sandbox error: {exc}", data={"blocked": True})
        payload = {
            "command": command,
            "exit_code": res.exit_code,
            "stdout": res.stdout[-8000:],
            "stderr": res.stderr[-8000:],
            "duration_ms": res.duration_ms,
            "timed_out": res.timed_out,
            "oom_killed": res.oom_killed,
        }
        return ToolResult(
            ok=res.exit_code == 0,
            data=payload,
            error=None if res.exit_code == 0 else f"exit {res.exit_code}",
        )

    def run_tests(a: RunTestsArgs) -> ToolResult:
        command = a.command or ctx.test_command
        if not command:
            return ToolResult(ok=False, error="no test command detected", data={"blocked": True})
        result = _run(command, timeout_s=None)
        result.data.update(
            _parse_pytest(
                SandboxResult(
                    result.data.get("exit_code", 1),
                    result.data.get("stdout", ""),
                    result.data.get("stderr", ""),
                    result.data.get("duration_ms", 0),
                )
            )
        )
        result.data["framework"] = command[0]
        return result

    def run_linter(_a: NoArgs) -> ToolResult:
        if not ctx.lint_command:
            return ToolResult(ok=True, data={"skipped": "no linter configured"})
        return _run(ctx.lint_command)

    def run_formatter(_a: NoArgs) -> ToolResult:
        if not ctx.format_command:
            return ToolResult(ok=True, data={"skipped": "no formatter configured"})
        return _run(ctx.format_command)

    def run_security_scan(a: RunSecurityScanArgs) -> ToolResult:
        results: dict[str, dict] = {}
        matrix = {
            "bandit": ["bandit", "-r", ".", "-f", "json", "-q"],
            "pip_audit": ["pip-audit", "-f", "json", "--progress-spinner", "off"],
            "semgrep": ["semgrep", "--config", "auto", "--json", "--quiet", "."],
            "npm_audit": ["npm", "audit", "--json"],
        }
        for name in a.tools:
            cmd = matrix.get(name)
            if not cmd:
                continue
            r = _run(cmd, timeout_s=120)
            parsed: dict = {"raw_exit": r.data.get("exit_code")}
            try:
                parsed["report"] = json.loads(r.data.get("stdout") or "{}")
            except json.JSONDecodeError:
                parsed["report"] = None
            results[name] = parsed
        return ToolResult(ok=True, data={"scans": results})

    return [
        Tool("run_tests", "Run the test suite in the sandbox.", RunTestsArgs, run_tests),
        Tool("run_linter", "Run the linter/type-checker in the sandbox.", NoArgs, run_linter),
        Tool("run_formatter", "Run the code formatter in the sandbox.", NoArgs, run_formatter),
        Tool(
            "run_security_scan",
            "Run security scanners in the sandbox.",
            RunSecurityScanArgs,
            run_security_scan,
        ),
    ]


def make_runner_or_none(language: str) -> SandboxRunner | None:
    from app.config import get_settings

    if get_settings().sandbox_disabled:
        return None
    try:
        return SandboxRunner(SandboxConfig.for_language(language))
    except SandboxError:
        return None

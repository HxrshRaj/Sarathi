from pathlib import Path

from worker.tools.base import Tool, ToolRegistry, ToolResult
from worker.tools.fs_tools import WorkspaceFS, build_fs_tools
from pydantic import BaseModel


class EchoArgs(BaseModel):
    value: str


def _echo(a: EchoArgs) -> ToolResult:
    return ToolResult(ok=True, data={"echo": a.value})


def test_unknown_tool_returns_error():
    reg = ToolRegistry(allow_mutations=True)
    res = reg.invoke("nope", {})
    assert not res.ok and "Unknown tool" in res.error


def test_invalid_args_rejected():
    reg = ToolRegistry(allow_mutations=True)
    reg.register(Tool("echo", "echo", EchoArgs, _echo))
    res = reg.invoke("echo", {"wrong": 1})
    assert not res.ok and "Invalid arguments" in res.error


def test_mutating_tool_disabled_without_permission(tmp_path: Path):
    fs = WorkspaceFS(tmp_path)
    reg = ToolRegistry(allow_mutations=False)
    reg.register_many(build_fs_tools(fs))
    res = reg.invoke("create_file", {"path": "x.py", "content": "1"})
    assert not res.ok and "disabled" in res.error
    assert not (tmp_path / "x.py").exists()


def test_mutating_tool_allowed_with_permission(tmp_path: Path):
    fs = WorkspaceFS(tmp_path)
    reg = ToolRegistry(allow_mutations=True)
    reg.register_many(build_fs_tools(fs))
    res = reg.invoke("create_file", {"path": "x.py", "content": "print(1)\n"})
    assert res.ok
    assert (tmp_path / "x.py").read_text() == "print(1)\n"


def test_specs_hide_mutating_tools_when_disallowed(tmp_path: Path):
    fs = WorkspaceFS(tmp_path)
    reg = ToolRegistry(allow_mutations=False)
    reg.register_many(build_fs_tools(fs))
    names = {s.name for s in reg.specs()}
    assert "read_file" in names
    assert "edit_file" not in names


def test_calls_are_recorded(tmp_path: Path):
    fs = WorkspaceFS(tmp_path)
    reg = ToolRegistry(allow_mutations=True)
    reg.register_many(build_fs_tools(fs))
    reg.invoke("list_files", {"path": ""})
    assert reg.calls and reg.calls[-1]["tool"] == "list_files"

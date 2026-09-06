"""Filesystem tools, jailed to the run workspace.

Editing model: exact-match search/replace edits (`old_string` → `new_string`),
not model-authored diff hunks — deterministic to apply and trivial to reject
cleanly (ADR-006). The unified diff is computed by us for the record.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from pydantic import BaseModel, Field

from worker.tools.base import Tool, ToolError, ToolResult, resolve_in_workspace

_MAX_READ_BYTES = 200_000
_MAX_LIST = 400


class ChangeRecord(BaseModel):
    path: str
    change_type: str  # create | modify | delete
    before_content: str | None
    after_content: str | None
    diff: str
    lines_added: int
    lines_removed: int


def _write(target: Path, content: str) -> None:
    """Write text without platform newline translation (keep LF on Windows)."""
    target.write_text(content, encoding="utf-8", newline="")


def _unified(path: str, before: str, after: str) -> tuple[str, int, int]:
    b = before.splitlines(keepends=True)
    a = after.splitlines(keepends=True)
    diff = list(difflib.unified_diff(b, a, fromfile=f"a/{path}", tofile=f"b/{path}"))
    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    return "".join(diff), added, removed


class WorkspaceFS:
    """Backs the fs tools and accumulates change records for persistence."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.changes: dict[str, ChangeRecord] = {}

    # -- primitives -----------------------------------------------------------
    def read(self, rel: str) -> str:
        target = resolve_in_workspace(self.workspace, rel)
        if not target.is_file():
            raise ToolError(f"File not found: {rel}")
        data = target.read_bytes()
        if len(data) > _MAX_READ_BYTES:
            raise ToolError(f"File too large to read ({len(data)} bytes)")
        return data.decode("utf-8", errors="replace")

    def _record(self, rel: str, before: str | None, after: str | None) -> ChangeRecord:
        original = self.changes[rel].before_content if rel in self.changes else before
        if after is None:
            diff, added, removed = _unified(rel, original or "", "")
            ct = "delete"
        elif original is None:
            diff, added, removed = _unified(rel, "", after)
            ct = "create"
        else:
            diff, added, removed = _unified(rel, original, after)
            ct = "modify"
        rec = ChangeRecord(
            path=rel,
            change_type=ct,
            before_content=original,
            after_content=after,
            diff=diff,
            lines_added=added,
            lines_removed=removed,
        )
        self.changes[rel] = rec
        return rec

    def create(self, rel: str, content: str) -> ChangeRecord:
        target = resolve_in_workspace(self.workspace, rel)
        if target.exists():
            raise ToolError(f"File already exists: {rel} (use edit_file)")
        target.parent.mkdir(parents=True, exist_ok=True)
        _write(target, content)
        return self._record(rel, None, content)

    def edit(self, rel: str, edits: list[tuple[str, str]]) -> ChangeRecord:
        before = self.read(rel)
        after = before
        for old, new in edits:
            if old == new:
                continue
            count = after.count(old)
            if count == 0:
                raise ToolError(f"`old_string` not found in {rel}: {old[:80]!r}")
            if count > 1:
                raise ToolError(
                    f"`old_string` is ambiguous in {rel} ({count} matches); add more context"
                )
            after = after.replace(old, new, 1)
        if after == before:
            raise ToolError("Edit produced no change")
        _write(resolve_in_workspace(self.workspace, rel), after)
        return self._record(rel, before, after)

    def delete(self, rel: str) -> ChangeRecord:
        target = resolve_in_workspace(self.workspace, rel)
        if not target.is_file():
            raise ToolError(f"File not found: {rel}")
        before = target.read_text("utf-8", errors="replace")
        target.unlink()
        return self._record(rel, before, None)

    def list_dir(self, rel: str) -> list[str]:
        base = resolve_in_workspace(self.workspace, rel or ".")
        if not base.is_dir():
            raise ToolError(f"Not a directory: {rel}")
        out: list[str] = []
        for p in sorted(base.rglob("*")):
            if any(part in {".git", "node_modules", ".venv", "__pycache__"} for part in p.parts):
                continue
            out.append(p.relative_to(self.workspace).as_posix() + ("/" if p.is_dir() else ""))
            if len(out) >= _MAX_LIST:
                break
        return out


# ── arg models ───────────────────────────────────────────────────────────────
class ReadFileArgs(BaseModel):
    path: str


class ListFilesArgs(BaseModel):
    path: str = Field(default="", description="directory relative to repo root; empty = root")


class CreateFileArgs(BaseModel):
    path: str
    content: str


class EditOp(BaseModel):
    old_string: str = Field(description="exact text to replace; must occur exactly once")
    new_string: str


class EditFileArgs(BaseModel):
    path: str
    edits: list[EditOp] = Field(min_length=1)


class DeleteFileArgs(BaseModel):
    path: str


def build_fs_tools(fs: WorkspaceFS) -> list[Tool]:
    def read_file(a: ReadFileArgs) -> ToolResult:
        return ToolResult(ok=True, data={"path": a.path, "content": fs.read(a.path)})

    def list_files(a: ListFilesArgs) -> ToolResult:
        return ToolResult(ok=True, data={"entries": fs.list_dir(a.path)})

    def create_file(a: CreateFileArgs) -> ToolResult:
        rec = fs.create(a.path, a.content)
        return ToolResult(ok=True, data={"change": rec.model_dump()})

    def edit_file(a: EditFileArgs) -> ToolResult:
        rec = fs.edit(a.path, [(e.old_string, e.new_string) for e in a.edits])
        return ToolResult(ok=True, data={"change": rec.model_dump()})

    def delete_file(a: DeleteFileArgs) -> ToolResult:
        rec = fs.delete(a.path)
        return ToolResult(ok=True, data={"change": rec.model_dump()})

    return [
        Tool("read_file", "Read a UTF-8 text file from the repository.", ReadFileArgs, read_file),
        Tool(
            "list_files",
            "List files under a directory (recursive, capped).",
            ListFilesArgs,
            list_files,
        ),
        Tool(
            "create_file",
            "Create a new file with the given content.",
            CreateFileArgs,
            create_file,
            mutating=True,
        ),
        Tool(
            "edit_file",
            "Apply exact search/replace edits to a file.",
            EditFileArgs,
            edit_file,
            mutating=True,
        ),
        Tool(
            "delete_file",
            "Delete a file from the repository.",
            DeleteFileArgs,
            delete_file,
            mutating=True,
        ),
    ]

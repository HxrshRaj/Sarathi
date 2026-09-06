from pathlib import Path

import pytest

from worker.tools.base import ToolError
from worker.tools.fs_tools import WorkspaceFS


def test_edit_exact_match(tmp_path: Path):
    (tmp_path / "a.py").write_text("value = 1\nother = 2\n")
    fs = WorkspaceFS(tmp_path)
    rec = fs.edit("a.py", [("value = 1", "value = 42")])
    assert (tmp_path / "a.py").read_text() == "value = 42\nother = 2\n"
    assert rec.change_type == "modify"
    assert rec.lines_added == 1 and rec.lines_removed == 1
    assert "-value = 1" in rec.diff and "+value = 42" in rec.diff


def test_edit_ambiguous_match_rejected(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\nx = 1\n")
    fs = WorkspaceFS(tmp_path)
    with pytest.raises(ToolError, match="ambiguous"):
        fs.edit("a.py", [("x = 1", "x = 2")])


def test_edit_missing_anchor_rejected(tmp_path: Path):
    (tmp_path / "a.py").write_text("hello\n")
    fs = WorkspaceFS(tmp_path)
    with pytest.raises(ToolError, match="not found"):
        fs.edit("a.py", [("goodbye", "hi")])


def test_create_then_edit_tracks_original_before(tmp_path: Path):
    fs = WorkspaceFS(tmp_path)
    fs.create("n.py", "a = 1\n")
    fs.edit("n.py", [("a = 1", "a = 2")])
    rec = fs.changes["n.py"]
    assert rec.change_type == "create"  # net change vs original (which was absent)
    assert rec.after_content == "a = 2\n"


def test_delete_records_before(tmp_path: Path):
    (tmp_path / "d.py").write_text("bye\n")
    fs = WorkspaceFS(tmp_path)
    rec = fs.delete("d.py")
    assert rec.change_type == "delete"
    assert rec.before_content == "bye\n"
    assert not (tmp_path / "d.py").exists()


def test_create_existing_file_rejected(tmp_path: Path):
    (tmp_path / "e.py").write_text("1\n")
    fs = WorkspaceFS(tmp_path)
    with pytest.raises(ToolError, match="already exists"):
        fs.create("e.py", "2\n")

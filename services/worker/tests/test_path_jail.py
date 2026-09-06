from pathlib import Path

import pytest

from worker.tools.base import ToolError, resolve_in_workspace


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    return tmp_path


def test_allows_normal_relative_path(ws: Path):
    p = resolve_in_workspace(ws, "src/a.py")
    assert p == (ws / "src" / "a.py").resolve()


def test_allows_nested_new_path(ws: Path):
    p = resolve_in_workspace(ws, "src/new/deep/file.py")
    assert str(p).startswith(str(ws.resolve()))


@pytest.mark.parametrize(
    "bad",
    [
        "../outside.txt",
        "src/../../etc/passwd",
        "/etc/passwd",
        "\\\\server\\share",
        "src/a\x00.py",
        "..",
        "src/../..",
    ],
)
def test_rejects_escapes(ws: Path, bad: str):
    with pytest.raises(ToolError):
        resolve_in_workspace(ws, bad)


def test_rejects_windows_reserved_names(ws: Path):
    for name in ("CON", "nul.txt", "com1", "LPT9.log"):
        with pytest.raises(ToolError):
            resolve_in_workspace(ws, name)


def test_rejects_symlink_pointing_outside(ws: Path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    link = ws / "escape"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform/user")
    with pytest.raises(ToolError):
        resolve_in_workspace(ws, "escape/secret.txt")


def test_empty_path_rejected(ws: Path):
    with pytest.raises(ToolError):
        resolve_in_workspace(ws, "")

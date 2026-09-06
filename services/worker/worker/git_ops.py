"""Trusted-side git operations. Runs on the worker host, never in the sandbox.

The OAuth token is injected only into the remote URL for the duration of a fetch
and is scrubbed from the stored remote afterwards.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.logging import get_logger

log = get_logger("git_ops")

_TIMEOUT = 300


class GitError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(  # noqa: S603 - args are a fixed list, never shell
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:500]}")
    return proc.stdout.strip()


def _authed_url(clone_url: str, token: str | None) -> str:
    if not token or not clone_url.startswith("https://"):
        return clone_url
    return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)


def clone_at(clone_url: str, dest: Path, *, ref: str, token: str | None = None) -> str:
    """Shallow-clone `ref` into `dest`. Returns the resolved commit sha."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["clone", "--filter=blob:none", "--no-checkout", _authed_url(clone_url, token), str(dest)])
    _run(["remote", "set-url", "origin", clone_url], cwd=dest)  # scrub token
    _run(["fetch", "--depth", "1", "origin", ref], cwd=dest) if token is None else _run(
        [
            "-c",
            f"http.extraheader=AUTHORIZATION: bearer {token}",
            "fetch",
            "--depth",
            "1",
            "origin",
            ref,
        ],
        cwd=dest,
    )
    _run(["checkout", "FETCH_HEAD"], cwd=dest)
    return _run(["rev-parse", "HEAD"], cwd=dest)


def init_work_branch(repo_dir: Path, branch: str) -> None:
    _run(["checkout", "-b", branch], cwd=repo_dir)


def stage_all(repo_dir: Path) -> None:
    _run(["add", "-A"], cwd=repo_dir)


def commit(repo_dir: Path, message: str, *, author_name: str, author_email: str) -> str:
    _run(
        [
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
            "--no-verify",
        ],
        cwd=repo_dir,
    )
    return _run(["rev-parse", "HEAD"], cwd=repo_dir)


def push_branch(repo_dir: Path, clone_url: str, branch: str, token: str) -> None:
    _run(
        ["-c", f"http.extraheader=AUTHORIZATION: bearer {token}", "push", "origin", branch],
        cwd=repo_dir,
    )


def diff_stat(repo_dir: Path) -> str:
    return _run(["diff", "--stat", "HEAD"], cwd=repo_dir)

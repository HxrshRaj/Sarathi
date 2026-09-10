"""Trusted-side git operations. Runs on the worker host, never in the sandbox.

The OAuth token is injected only into the remote URL for the duration of a fetch
and is scrubbed from the stored remote afterwards.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.logging import get_logger

log = get_logger("git_ops")

_TIMEOUT = 300

# Never let git block on an interactive credential prompt — there is no console
# under the worker / MCP server, so a helper would hang until the timeout. Fail
# fast instead (public repos still clone; private repos need an explicit token).
_NONINTERACTIVE_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
_NONINTERACTIVE_ARGS = ["-c", "credential.helper=", "-c", "core.askpass="]


class GitError(RuntimeError):
    pass


def _run(args: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
    try:
        proc = subprocess.run(  # noqa: S603 - args are a fixed list, never shell
            ["git", *_NONINTERACTIVE_ARGS, *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout or _TIMEOUT,
            env=_NONINTERACTIVE_ENV,
            # Detach stdin: when git is spawned from a server whose stdin is a
            # transport pipe (the MCP stdio server), an inherited stdin handle
            # can make even `git --version` hang on Windows.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out after {exc.timeout:g}s") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:500]}")
    return proc.stdout.strip()


def _authed_url(clone_url: str, token: str | None) -> str:
    if not token or not clone_url.startswith("https://"):
        return clone_url
    return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)


def clone_at(
    clone_url: str,
    dest: Path,
    *,
    ref: str,
    token: str | None = None,
    depth: int | None = None,
    timeout: int | None = None,
    blobless: bool = True,
) -> str:
    """Clone `clone_url` into `dest` and check out `ref` (a branch or a commit sha).

    Returns the resolved commit sha. Any token is used only for the initial clone
    and immediately scrubbed from the stored remote. `depth` shallow-clones (only
    safe for real remotes that allow fetch-by-sha, e.g. GitHub); `timeout` bounds
    each git invocation; `blobless=False` fetches file contents up front (faster
    when the caller needs a full working tree, e.g. a one-off structure scan).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    clone_args = ["clone", "--no-checkout"]
    if blobless:
        clone_args.insert(1, "--filter=blob:none")
    if depth:
        clone_args += ["--depth", str(depth)]
    _run([*clone_args, _authed_url(clone_url, token), str(dest)], timeout=timeout)
    _run(["remote", "set-url", "origin", clone_url], cwd=dest, timeout=timeout)  # scrub token

    # A full-ish clone already has every branch + (usually) the wanted commit.
    try:
        _run(["checkout", "--detach", ref], cwd=dest, timeout=timeout)
        return _run(["rev-parse", "HEAD"], cwd=dest, timeout=timeout)
    except GitError:
        pass

    fetch_prefix = (
        [] if token is None else ["-c", f"http.extraheader=AUTHORIZATION: bearer {token}"]
    )
    fetch_args = [*fetch_prefix, "fetch"]
    if depth:
        fetch_args += ["--depth", str(depth)]
    _run([*fetch_args, "origin", ref], cwd=dest, timeout=timeout)
    _run(["checkout", "--detach", "FETCH_HEAD"], cwd=dest, timeout=timeout)
    return _run(["rev-parse", "HEAD"], cwd=dest, timeout=timeout)


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

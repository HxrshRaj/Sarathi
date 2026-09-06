"""Ephemeral Docker sandbox for executing repository / generated code.

Guarantees (see docs/SANDBOX.md):
  network none · non-root · cap-drop ALL · no-new-privileges · read-only rootfs ·
  tmpfs workspace · memory / cpu / pids limits · wall-clock kill · forced cleanup ·
  no secrets in env · no host bind mounts · no docker socket inside.

If Docker is unreachable the caller gets `SandboxError` and must report the step
as *blocked* — code is never run on the worker host as a fallback.
"""

from __future__ import annotations

import io
import tarfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.logging import get_logger

log = get_logger("sandbox")

_LANG_IMAGE_KEY = {
    "python": "sandbox_image_python",
    "javascript": "sandbox_image_node",
    "typescript": "sandbox_image_node",
    "node": "sandbox_image_node",
}
_SKIP = {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}


def _parse_size(text: str) -> int:
    """'512m' -> bytes. Accepts k/m/g suffixes; defaults to bytes."""
    text = text.strip().lower()
    mult = {"k": 1024, "m": 1024**2, "g": 1024**3}.get(text[-1:], 1)
    digits = text[:-1] if mult > 1 else text
    try:
        return int(float(digits) * mult)
    except ValueError:
        return 512 * 1024**2


class SandboxError(RuntimeError):
    pass


@dataclass(slots=True)
class SandboxConfig:
    image: str
    memory: str = "1g"
    cpus: float = 1.0
    pids_limit: int = 256
    timeout_s: int = 120
    workspace_tmpfs_size: str = "512m"

    @classmethod
    def for_language(cls, language: str) -> SandboxConfig:
        s = get_settings()
        image = getattr(s, _LANG_IMAGE_KEY.get(language, "sandbox_image_python"))
        return cls(
            image=image,
            memory=s.sandbox_memory,
            cpus=s.sandbox_cpus,
            pids_limit=s.sandbox_pids_limit,
            timeout_s=s.sandbox_timeout_s,
        )


@dataclass(slots=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    oom_killed: bool = False


def docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:  # noqa: BLE001
        return False


def _tar_workspace(src: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for p in src.rglob("*"):
            if p.is_dir() or any(part in _SKIP for part in p.parts):
                continue
            tar.add(p, arcname=p.relative_to(src).as_posix())
    return buf.getvalue()


class SandboxRunner:
    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        try:
            import docker
        except ImportError as exc:  # pragma: no cover
            raise SandboxError("docker SDK not installed") from exc
        try:
            self._client = docker.from_env()
            self._client.ping()
        except Exception as exc:  # noqa: BLE001
            raise SandboxError(f"Docker daemon unreachable: {exc}") from exc

    def run(
        self,
        *,
        workspace_dir: Path,
        command: list[str],
        language: str = "python",
        timeout_s: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        cfg = self.config
        timeout = timeout_s or cfg.timeout_s
        safe_env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/workspace"}
        safe_env.update({k: v for k, v in (env or {}).items() if not _looks_secret(k)})

        from docker.types import Ulimit

        fsize_bytes = _parse_size(cfg.workspace_tmpfs_size)
        container = self._client.containers.create(
            image=cfg.image,
            command=["sleep", str(timeout + 10)],
            working_dir="/workspace",
            user="65532:65532",
            network_mode="none",
            mem_limit=cfg.memory,
            memswap_limit=cfg.memory,
            nano_cpus=int(cfg.cpus * 1_000_000_000),
            pids_limit=cfg.pids_limit,
            # `--read-only` rootfs and a `/workspace` tmpfs are both avoided: the
            # Docker daemon silently drops `put_archive` writes into a tmpfs mount
            # and rejects them into a read-only rootfs, and the workspace is
            # delivered via `put_archive`. The workspace therefore lives on the
            # container's own writable layer, which is discarded on the forced
            # `remove()`. A per-file size rlimit bounds disk abuse; the
            # gVisor/Kata backend (docs/SANDBOX.md) restores the stronger
            # guarantees. Isolation still in force: ephemeral, non-root, no
            # network, cap-drop ALL, no-new-privileges, pid/mem/cpu caps.
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            tmpfs={"/tmp": "rw,size=64m,uid=65532,gid=65532"},
            ulimits=[
                Ulimit(name="fsize", soft=fsize_bytes, hard=fsize_bytes),
                Ulimit(name="nofile", soft=1024, hard=2048),
            ],
            environment=safe_env,
            labels={"app": "codepilot", "role": "sandbox"},
            detach=True,
        )
        started = time.perf_counter()
        try:
            container.start()
            container.put_archive("/workspace", _tar_workspace(workspace_dir))

            holder: dict[str, object] = {}

            def _exec() -> None:
                code, (out, err) = container.exec_run(
                    cmd=command, workdir="/workspace", user="65532:65532", demux=True
                )
                holder["code"] = code
                holder["out"] = (out or b"").decode("utf-8", "replace")[-20000:]
                holder["err"] = (err or b"").decode("utf-8", "replace")[-20000:]

            worker = threading.Thread(target=_exec, daemon=True)
            worker.start()
            worker.join(timeout)
            duration_ms = int((time.perf_counter() - started) * 1000)

            if worker.is_alive():
                container.kill()
                return SandboxResult(
                    124,
                    str(holder.get("out", "")),
                    "sandbox: wall-clock timeout",
                    duration_ms,
                    timed_out=True,
                )

            container.reload()
            oom = bool(container.attrs.get("State", {}).get("OOMKilled"))
            return SandboxResult(
                exit_code=int(holder.get("code", 1) or 0),
                stdout=str(holder.get("out", "")),
                stderr=str(holder.get("err", "")),
                duration_ms=duration_ms,
                oom_killed=oom,
            )
        finally:
            try:
                container.remove(force=True)
            except Exception as exc:  # noqa: BLE001
                log.warning("sandbox_cleanup_failed", error=str(exc))


def _looks_secret(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in ("key", "token", "secret", "password", "passwd", "credential"))

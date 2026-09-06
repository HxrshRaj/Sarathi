# Sandbox security model

Generated code and repository code are **never executed in the worker process**.
Execution happens in a throwaway Docker container launched by the worker.

## Container configuration

Every execution (`run_tests`, `run_linter`, `run_formatter`, `run_security_scan`,
build/import checks) is one container run:

| Control | Setting | Purpose |
|---|---|---|
| Image | `codepilot/sandbox:<lang>` pinned digest | known, minimal toolchain |
| Network | `--network none` | no egress, no lateral movement |
| User | non-root `sandbox` UID 65532 | drop privileges |
| Capabilities | `--cap-drop ALL` | remove all Linux caps |
| Privilege escalation | `--security-opt no-new-privileges` | block setuid |
| Root FS | writable (see note) | — |
| Workspace | `tmpfs` at `/workspace` + `/tmp`, size-capped, uid-scoped | writable scratch, discarded on exit |
| Memory | `--memory=1g --memory-swap=1g` | OOM-kill runaway |
| CPU | `--cpus=1.0` | bound compute |
| PIDs | `--pids-limit=256` | block fork bombs |
| ulimits | file size, nofile | bound disk/fd |
| Wall clock | worker kills + `--stop-timeout` after `SANDBOX_TIMEOUT_S` (default 120) | bound runtime |
| Cleanup | `--rm` + explicit `force remove` in `finally` | no residue |
| Env | only `PATH`, `LANG`, task-relevant non-secret vars | no secrets, no DB creds, no tokens |
| Mounts | workspace only (rw). **No `docker.sock`. No host paths.** | no host access |

**Note on `--read-only` rootfs:** not applied. The Docker daemon rejects
`put_archive` / `docker cp` into a `--read-only` container even when the target is
a `tmpfs` mount, and the workspace is delivered via `put_archive`. The container
is still ephemeral, non-root, no-network, `--cap-drop ALL`,
`--security-opt no-new-privileges`, with pid/mem/cpu caps and forced removal — a
writable rootfs inside a throwaway non-root no-network container is an acceptable
v1 posture. The gVisor/Kata upgrade path (below) restores an immutable base.

Implemented in `services/worker/sandbox/runner.py` via the Docker SDK. The public
API is:

```python
result = SandboxRunner(config).run(
    workspace_dir=Path(...),      # copied into the container's tmpfs
    command=["pytest", "-q"],     # argv, never a shell string
    language="python",
    timeout_s=120,
)
# -> SandboxResult(exit_code, stdout, stderr, duration_ms, timed_out, oom_killed)
```

`command` is always an argv list executed without a shell. There is no
`run_shell` tool anywhere in the system.

## Workspace handling
1. Worker checks out the repo snapshot to `RUN_WORKSPACE_ROOT/<run_id>/` on a
   host volume (trusted side, not executed).
2. Agent file tools edit that directory (path-jailed).
3. For each execution the relevant subtree is `tar`-streamed into a fresh
   container's tmpfs; results stream back; container is destroyed.
4. On run completion the host workspace is retained for diffing/replay, then
   garbage-collected by a periodic Celery beat job after `WORKSPACE_TTL_H`.

## Dependency installation
- If the repo has a lockfile (`poetry.lock`, `requirements*.txt` with hashes,
  `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`): the worker pre-fetches
  packages on the trusted side into a cache dir, mounts it read-only, and the
  sandbox installs `--offline` / `--no-index` from it.
- No lockfile → dependency install is **skipped and reported**; tests that need
  uninstalled deps are marked `blocked`, not silently failed.
- `pip-audit` / `npm audit` advisories → `security_findings`.

## Threats addressed
Sandbox escape, network exfiltration, fork/OOM/disk DoS, host FS access, docker
socket abuse, secret theft from env, persistence across runs. See
[THREAT_MODEL.md](THREAT_MODEL.md) T2/T7/T8.

## Production upgrade path
Docker namespaces are a **soft** boundary. For multi-tenant production, swap
`SandboxRunner`'s backend for one of:
- **gVisor** (`runsc` runtime) — user-space kernel, drop-in runtime flag.
- **Kata Containers** — lightweight VM per container.
- **Firecracker** microVMs via `firecracker-containerd`.
The `SandboxRunner` interface is designed so this is a backend swap, not a
rewrite.

## Windows/dev note
On Docker Desktop (WSL2) the worker container mounts the daemon socket at
`/var/run/docker.sock`. `--network none`, rlimits and `tmpfs` all apply through
the Linux VM. `noexec` on the workspace tmpfs is not used (tests need to exec
interpreters); isolation relies on `network none` + caps + non-root + rlimits.

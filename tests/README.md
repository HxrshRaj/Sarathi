# Tests

Test code lives next to what it covers:

| Suite | Location | Needs |
|---|---|---|
| Worker unit (path jail, secret redaction, chunker, tool registry, fs edits, budget, fake LLM, sandbox hardening flags, prompt safety) | `services/worker/tests/` | nothing — pure logic |
| API unit/integration (health, error envelope, auth, row‑level authz, task flow, event‑schema compat) | `apps/api/tests/` | Postgres+pgvector via `DATABASE_URL_SYNC` (DB‑backed tests skip if unreachable) |
| Frontend unit (diff renderer) | `apps/web/lib/*.test.ts` | node + pnpm |
| Security corpus | `tests/security/prompt_injection/` | consumed by `services/worker/tests/test_prompt_safety.py` |

Run everything: `make test`. CI (`.github/workflows/ci.yml`) runs all suites plus
`bandit`, `pip-audit`, `gitleaks`, and image builds.

## Security testing focus

- **Prompt injection** — the corpus in `security/prompt_injection/` must be
  treated as data. Guarded by asserting the safety preamble is present on every
  agent prompt and that repo‑derived text is redacted of secrets.
- **Path traversal** — `test_path_jail.py` covers `..`, absolute paths, NUL
  bytes, Windows device names, and symlink escape.
- **Secret leakage** — `test_secrets.py` covers provider keys, private‑key
  headers, connection‑string passwords, high‑entropy tokens, and false‑positive
  resistance on prose.
- **Sandbox** — `test_sandbox_config.py` asserts the hardening flags are present
  and that no `shell`/`exec` tool exists anywhere in the tool layer.

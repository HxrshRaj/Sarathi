# Deploy — free tier (Vercel + Hugging Face Space)

A $0, no-card deploy: **Vercel** for the Next.js frontend, a **Hugging Face
Space** (Docker) for the FastAPI API + Celery worker, **Neon** for
Postgres/pgvector, **Upstash** for Redis.

### What works vs the local stack

| | Local `docker compose` | This free deploy |
|---|---|---|
| UI, auth, repos, tasks, SSE run view, diff, review, PRs | ✅ | ✅ |
| Hybrid retrieval / indexing | ✅ (gemini or fastembed embeddings) | ✅ (`hash` embeddings — no quota, no model download) |
| MCP server | ✅ | n/a (stdio — run it locally against the Neon DB) |
| **Code sandbox — running tests in agent runs** | ✅ | ❌ reported as **blocked** (a Space has no Docker daemon) |

The last row is the only real limitation. Everything else is a live, shareable URL.

---

## 1. Postgres — Neon (no card)

1. neon.tech → new project, region near you. Enable the **pgvector** extension is
   automatic on first `CREATE EXTENSION` (the migration does it).
2. Copy the connection string. You need two forms:
   - `DATABASE_URL` = `postgresql+asyncpg://USER:PASS@HOST/db?sslmode=require`
   - `DATABASE_URL_SYNC` = `postgresql+psycopg://USER:PASS@HOST/db?sslmode=require`
   (same creds; only the driver prefix differs). Use the **pooled** host.

## 2. Redis — Upstash (no card)

1. upstash.com → create a Redis database (global or a region near the Space).
2. Copy the **`rediss://…`** URL → this is `REDIS_URL`.

## 3. GitHub OAuth app

github.com/settings/developers → your existing app (or a new one):
- **Homepage URL:** `https://<project>.vercel.app`
- **Authorization callback URL:** `https://<owner>-sarathi-api.hf.space/api/auth/github/callback`
- Turn **“Expire user access tokens” OFF** (no refresh flow implemented).

## 4. Hugging Face Space (API + worker)

1. huggingface.co → New Space → **SDK: Docker**, name it `sarathi-api`, **public**.
2. `git clone` the Space, copy in the three files from
   [`deploy/hf-space/`](../deploy/hf-space) (`Dockerfile`, `start.sh`, `README.md`),
   commit, push.
3. Space **Settings → Variables and secrets** — add everything from
   [`deploy/hf-space/README.md`](../deploy/hf-space/README.md#set-these-as-space-secrets).
   Generate `ENCRYPTION_KEY` with:
   ```
   python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
   ```
4. The Space builds and boots (~3–5 min). Check `https://<owner>-sarathi-api.hf.space/api/health/ready`
   → `database: ok`, `redis: ok`.

> Free Spaces sleep after 48 h idle; first hit after a sleep cold-starts (~30 s).

## 5. Vercel (frontend)

1. vercel.com → New Project → import `HxrshRaj/Sarathi`.
2. **Root Directory:** `apps/web`  ·  Framework preset: **Next.js** (auto).
3. Environment variables:
   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | `https://<owner>-sarathi-api.hf.space` |
4. Deploy. Note the production URL — put it back into the Space's `WEB_BASE_URL`
   and `CORS_ORIGINS`, and into the GitHub OAuth app, then **factory-rebuild the
   Space** so it picks up the values.

## 6. First use

1. Open the Vercel URL → **Sign in with GitHub** → authorize → back to the
   dashboard as your GitHub user.
2. **Repositories** → connect one of yours → pick a branch → **Index**
   (uses `hash` embeddings; a minute or two).
3. **Tasks → New task** against that repo. The run streams live; test steps show
   `blocked`; the diff, security review and reviewer score are real; **Approve &
   open PR** works.

## Redeploying after code changes

- **Frontend:** Vercel redeploys on push to `main` automatically.
- **API/worker:** factory-rebuild the Space (it re-clones `main`), or pin
  `SARATHI_REF` to a commit in the Space Dockerfile build args.

## Notes / gotchas

- **Cross-site cookies:** `CROSS_SITE_COOKIES=true` makes the session cookie
  `SameSite=None; Secure` so it survives the Vercel↔Space hop. The browser talks
  to the Space directly (`NEXT_PUBLIC_API_BASE_URL`); CORS on the API allows the
  Vercel origin with credentials.
- **`ENV=production`** makes the API refuse to boot if any required secret is
  missing — the Space logs will name what's unset.
- **Costs:** Neon free (0.5 GB), Upstash free (10k cmd/day), HF Space free
  (2 vCPU / 16 GB, sleeps), Vercel Hobby. All no-card.

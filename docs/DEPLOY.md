# Deploy — free tier (Vercel + Render)

$0, no credit card: **Vercel** for the Next.js frontend, a **Render** free web
service for the FastAPI API + Celery worker, **Neon** for Postgres/pgvector,
**Upstash** for Redis.

> Hugging Face Spaces used to work for the backend but now require a paid plan
> for Docker/Gradio Spaces — hence Render. The old HF config is kept in
> `deploy/hf-space/` for anyone with HF Pro.

### What works vs the local stack

| | Local `docker compose` | Free deploy |
|---|---|---|
| UI, GitHub auth, repos, tasks, live SSE run view, diff, review, PRs | ✅ | ✅ |
| Hybrid retrieval / indexing | ✅ | ✅ (`hash` embeddings — no quota, no model download) |
| **Code sandbox — running tests in agent runs** | ✅ | ❌ reported **blocked** (no Docker daemon on free hosts) |
| MCP server (stdio) | ✅ | run locally against the Neon DB |

Render free also **sleeps after 15 min idle** (~40 s cold start) and is 512 MB —
fine for browsing + indexing a small repo; a heavy agent run may be slow.

---

## 1. Postgres — Neon (no card)

neon.tech → new project → copy the connection string in two forms (same creds,
different driver prefix), keep `?sslmode=require`:
- `DATABASE_URL` = `postgresql+asyncpg://USER:PASS@HOST/DB?sslmode=require`
- `DATABASE_URL_SYNC` = `postgresql+psycopg://USER:PASS@HOST/DB?sslmode=require`

## 2. Redis — Upstash (no card)

upstash.com → create Redis → copy the **`rediss://…`** URL → `REDIS_URL`.

## 3. GitHub OAuth app

github.com/settings/developers → your app:
- **Homepage URL:** `https://<project>.vercel.app`
- **Authorization callback URL:** `https://sarathi-api.onrender.com/api/auth/github/callback`
- **“Expire user access tokens” → OFF**

## 4. Render (API + worker)

**Option A — Blueprint:** Render dashboard → **New → Blueprint** → pick this repo.
It reads `render.yaml`, creates the `sarathi-api` web service. Then open the
service → **Environment** and fill every `sync: false` var (values/notes are in
`render.yaml`).

**Option B — manual:** New → **Web Service** → connect the repo →
- Runtime **Python 3**, Root Directory blank
- Build: `pip install -e "apps/api[worker]" -e "services/worker"`
- Start: `bash deploy/render/start.sh`
- Health check path: `/api/health`
- Add the env vars from `render.yaml` (the non‑`sync:false` ones as literals, the
  `sync:false` ones as your secrets).

Generate `ENCRYPTION_KEY`:
```
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
```

Deploy. Check `https://sarathi-api.onrender.com/api/health/ready` →
`database: ok`, `redis: ok`.

## 5. Vercel (frontend)

New Project → import the repo →
- **Root Directory:** `apps/web` · Framework: Next.js (auto)
- Env: `NEXT_PUBLIC_API_BASE_URL` = `https://sarathi-api.onrender.com`

Deploy, note the URL, put it back into the Render service's `WEB_BASE_URL` and
`CORS_ORIGINS` and the GitHub OAuth app, then **Manual Deploy → Clear build
cache & deploy** on Render.

## 6. First use

Vercel URL → **Sign in with GitHub** → **Repositories** → connect one → **Index**
→ **Tasks → New task**. Test steps show `blocked`; plan/retrieval/diff/review/PR
are real.

## Redeploy

- Frontend: Vercel auto-deploys on push to `main`.
- Backend: Render auto-deploys on push to `main` (or Manual Deploy).

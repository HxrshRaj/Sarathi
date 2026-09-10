---
title: Sarathi API
emoji: 🛠️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Sarathi API (Hugging Face Space)

Backend for [Sarathi](https://github.com/HxrshRaj/Sarathi) — FastAPI + the Celery
agent worker in one container. The frontend runs separately on Vercel.

**This is the Space repo.** It contains only `Dockerfile`, `start.sh` and this
README. The app code is cloned from GitHub at build time.

## Set these as Space *secrets* (Settings → Variables and secrets)

| Name | Value |
|---|---|
| `ENV` | `production` |
| `DATABASE_URL` | Neon pooled URL, `postgresql+asyncpg://…` |
| `DATABASE_URL_SYNC` | Neon URL, `postgresql+psycopg://…` |
| `REDIS_URL` | Upstash Redis URL, `rediss://…` |
| `ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `SESSION_SECRET` | any 32+ random chars |
| `GEMINI_API_KEY` | Google AI Studio key |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | your OAuth app |
| `API_BASE_URL` | `https://<owner>-sarathi-api.hf.space` (this Space's URL) |
| `WEB_BASE_URL` | `https://<project>.vercel.app` |
| `CORS_ORIGINS` | `https://<project>.vercel.app` |
| `CROSS_SITE_COOKIES` | `true` |
| `LLM_PROVIDER` | `gemini` |
| `LLM_DEFAULT_MODEL` | `gemini-3.5-flash` |
| `EMBEDDING_PROVIDER` | `hash` |
| `EMBEDDING_DIM` | `768` |

`SANDBOX_DISABLED=true` is baked into the image — a Space has no Docker daemon, so
agent runs plan / retrieve / edit / review / open PRs but test execution reports
"blocked".

## Rebuild after code changes

Factory rebuild the Space, or bump the pinned ref:
`Settings → Variables` → add build arg `SARATHI_REF` = a commit sha.

# ThriftFind — Deployment Guide

Topology: **Frontend on Vercel**, **Backend on Railway/Render**, **Database on Supabase (Postgres)**,
source on **GitHub**. Everything the backend needs is driven by environment variables — no code
changes between environments.

```
Browser ──> Vercel (static Vite frontend)
                │  fetch(VITE_API_BASE + /api/...)
                ▼
        Railway/Render (FastAPI, Docker)  ──>  Supabase (Postgres)
                │                          ──>  HuggingFace Inference API (sentiment)
                └──────────────────────────>  Groq API (chatbot phrasing)
```

---

## 1. Database — Supabase

1. Create a project at supabase.com. Set a strong DB password.
2. **Project Settings → Database → Connection string → URI.** Take the URI and add the SQLAlchemy
   driver prefix `postgresql+psycopg2://` (Supabase gives `postgresql://`):
   ```
   postgresql+psycopg2://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres
   ```
   This is your `DATABASE_URL`. (A long-running backend uses the direct 5432 connection.)
3. **Load the data once** — from your machine, pointed at Supabase:
   ```bash
   cd app/backend
   DATABASE_URL="postgresql+psycopg2://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres" \
     python -m app.seed
   ```
   `seed` creates the tables and loads `data/stores.json`. Re-running it **drops and recreates**
   all tables (destructive) — that's intended for a fresh load.

> Note: `create_all` (run at startup and by seed) can't *alter* existing tables. When you later
> change the schema, either reseed or add Alembic migrations (see PRODUCTION_READINESS.md P0-3).

---

## 2. Backend — Railway or Render (Docker)

The backend ships a `Dockerfile` at `app/backend/Dockerfile`; both platforms build it directly.

### Railway
1. New Project → Deploy from GitHub repo.
2. Service settings → **Root Directory: `app/backend`** (so the Dockerfile is detected).
3. Add the environment variables below. Railway injects `$PORT` automatically.

### Render
1. New → **Web Service** → connect the repo.
2. **Root Directory: `app/backend`**, Runtime: **Docker**.
3. Add the environment variables below. Render injects `$PORT` automatically.

### Backend environment variables
| Var | Value |
|-----|-------|
| `ENVIRONMENT` | `production` (makes a weak JWT secret a hard startup failure) |
| `DATABASE_URL` | the Supabase URI from step 1 |
| `FIRSTFIND_JWT_SECRET` | 32+ char secret — `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CORS_ORIGINS` | your Vercel URL, e.g. `https://thriftfind.vercel.app` (comma-separated for multiple) |
| `HUGGINGFACE_TOKEN` | your HF token (sentiment; falls back to VADER if unset) |
| `GROQ_API_KEY` | your Groq key (chatbot phrasing; falls back to rule-based if unset) |

After it boots, note the public URL (e.g. `https://thriftfind-api.up.railway.app`) — the frontend needs it.

---

## 3. Frontend — Vercel

1. New Project → import the repo.
2. **Root Directory: `app/frontend`** (Vercel auto-detects Vite; `vercel.json` sets build + SPA routing).
3. Environment variable:
   | Var | Value |
   |-----|-------|
   | `VITE_API_BASE` | the backend URL from step 2, no trailing slash |
4. Deploy. Then set `CORS_ORIGINS` on the backend to this Vercel domain and redeploy the backend.

> `VITE_*` vars are baked in at **build time** — after changing `VITE_API_BASE`, redeploy the frontend.

---

## 4. GitHub / CI

- Initialize the repo and push. `.gitignore` already excludes `.env`, `*.db`, `node_modules`, `dist`,
  and caches. **Never commit `.env`** — only `.env.example`.
- `.github/workflows/ci.yml` runs on every push/PR: backend lint (pyflakes) + both smoke harnesses
  (`_verify.py`, `_audit.py`) on a throwaway SQLite DB (no secrets needed), and a frontend `vite build`.

---

## 5. Post-deploy smoke check

```bash
# Backend health
curl https://<backend-url>/api/health           # {"status":"ok",...}
curl https://<backend-url>/api/stores            # list of stores

# Then in the browser: open the Vercel URL, register, browse, post a review,
# and confirm the store's sentiment meter updates within a few seconds
# (the HF call runs in a background task).
```

If sentiment stays unscored: check `HUGGINGFACE_TOKEN` on the backend and its logs. If the browser
shows CORS errors: `CORS_ORIGINS` must exactly match the Vercel origin (scheme + host, no path).

---

## 6. Known follow-ups (see PRODUCTION_READINESS.md)

- The in-memory rate limiter is per-process; run a single web instance or move to Redis before scaling out.
- Background tasks (sentiment/recommender) aren't durable — schedule the batch pipeline
  (`python -m app.ml.pipeline`) as a periodic job (Railway/Render cron) so anything missed is re-scored.
- Add Alembic before your first post-launch schema change.

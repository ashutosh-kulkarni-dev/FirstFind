0.# 🚀 Launch ThriftFind — Vercel (frontend) + Render (backend) + Supabase (DB)

A do-it-now checklist. Order matters (there's one deliberate two-pass step for CORS).
Everything is env-var driven — no code edits needed. Local commands are **Windows PowerShell**.

**You'll need accounts:** GitHub, Supabase, Render, Vercel. Have your `HUGGINGFACE_TOKEN` ready
(and optionally a `GROQ_API_KEY` for nicer chatbot replies — optional, it falls back without one).

---

## Step 0 — Push the repo to GitHub

From the repo root (`c:\Users\Ashutosh Kulkarni\ThriftFind`):

```powershell
git init
git add .
git commit -m "ThriftFind: initial deploy"
git branch -M main
git remote add origin https://github.com/<you>/thriftfind.git
git push -u origin main
```

> `.gitignore` already keeps `.env` and `*.db` out. Confirm `git status` does **not** list `app/backend/.env`.

---

## Step 1 — Database on Supabase

1. supabase.com → **New project**. Pick a region near Bengaluru, set a strong **DB password**, wait for it to provision.
2. **Project Settings → Database → Connection string → URI.** Copy it. It looks like:
   `postgresql://postgres:[PASSWORD]@db.abcdxyz.supabase.co:5432/postgres`
3. Turn it into your `DATABASE_URL` by adding the driver prefix and your password:
   ```
   postgresql+psycopg2://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres
   ```
   Keep this string handy — Render and the seed step both use it.

---

## Step 2 — Load the data (one time, from your machine)

This creates the tables and loads the stores into Supabase.

```powershell
cd "c:\Users\Ashutosh Kulkarni\ThriftFind\app\backend"
$env:DATABASE_URL = "postgresql+psycopg2://postgres:<PASSWORD>@db.<REF>.supabase.co:5432/postgres"
python -m app.seed
```

Expect: `Seeded: 131 stores (105 visible ...) | ... | 4 distinct zones`.
(If `psycopg2` isn't installed locally: `pip install psycopg2-binary`.)

---

## Step 3 — Generate a JWT secret

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the output — it's `FIRSTFIND_JWT_SECRET` for Render (production **requires** a strong one).

---

## Step 4 — Backend on Render

1. render.com → **New → Web Service** → connect your GitHub repo.
2. Settings:
   - **Root Directory:** `app/backend`
   - **Runtime / Language:** **Docker** (it auto-detects `app/backend/Dockerfile`)
   - **Instance type:** Free (fine to start)
   - **Health Check Path:** `/api/health`
3. **Environment → add these variables:**

   | Key | Value |
   |-----|-------|
   | `ENVIRONMENT` | `production` |
   | `DATABASE_URL` | your Supabase URI from Step 1 |
   | `FIRSTFIND_JWT_SECRET` | the secret from Step 3 |
   | `HUGGINGFACE_TOKEN` | your HF token |
   | `GROQ_API_KEY` | your Groq key *(optional — omit to use the offline chatbot)* |
   | `CORS_ORIGINS` | `https://placeholder.vercel.app` *(temporary — fixed in Step 6)* |

   > Don't set `PORT` — Render injects it and the Dockerfile already binds `0.0.0.0:$PORT`.
4. **Create Web Service.** When it's live, copy the URL, e.g. `https://thriftfind-api.onrender.com`.
5. Verify: open `https://<your-render-url>/api/health` → `{"status":"ok",...}`.

---

## Step 5 — Frontend on Vercel

1. vercel.com → **Add New → Project** → import the same GitHub repo.
2. Settings:
   - **Root Directory:** `app/frontend` (Vercel auto-detects Vite; `vercel.json` handles build + routing)
3. **Environment Variables → add:**

   | Key | Value |
   |-----|-------|
   | `VITE_API_BASE` | your Render URL from Step 4 (no trailing slash) |
4. **Deploy.** Copy the resulting URL, e.g. `https://thriftfind.vercel.app`.

---

## Step 6 — Wire CORS (the second pass)

1. Back in **Render → your service → Environment**, set:
   ```
   CORS_ORIGINS = https://thriftfind.vercel.app     ← your real Vercel URL
   ```
2. Save → Render redeploys automatically.

> Why: the browser calls Render cross-origin, so the backend must allow the exact Vercel origin
> (scheme + host, no trailing slash). Multiple origins? comma-separate them.

---

## Step 7 — Verify the live app

1. Open your Vercel URL.
2. **Register** an account → browse stores → open a store → **post a review**.
3. Within a few seconds the store's **sentiment meter** updates (the HF call runs in a background task).
4. Try the **chat** ("thrift stores in Koramangala", "what's open now").

Backend spot-checks:
```powershell
curl https://<your-render-url>/api/health
curl https://<your-render-url>/api/stores
```

---

## Troubleshooting

| Symptom | Fix |
|--------|-----|
| Browser console shows **CORS error** | `CORS_ORIGINS` on Render must exactly equal the Vercel origin (`https://…`, no path/slash). Redeploy after changing. |
| Frontend calls go to the wrong place / 404 | `VITE_API_BASE` wrong or missing. It's baked in at **build time** — fix it in Vercel and **redeploy the frontend**. |
| Backend won't start, logs say **SECURITY: JWT secret…** | `FIRSTFIND_JWT_SECRET` is missing/short. Set a 32+ char secret (Step 3). |
| Reviews never get a sentiment | Check `HUGGINGFACE_TOKEN` on Render + the service logs (it falls back to VADER if the token is bad). |
| First request after idle is slow (~50s) | Render Free spins down when idle; the first hit cold-starts. Upgrade the instance or ping it to keep warm. |
| DB connection errors | Recheck `DATABASE_URL` (must start `postgresql+psycopg2://`) and that Step 2 seeding succeeded. |

---

## Notes for later (not blockers)

- **Redeploys:** push to `main` → Render and Vercel auto-build. CI (`.github/workflows/ci.yml`) runs lint + smoke tests on every push.
- **Keep things fresh:** background sentiment/recommender aren't durable — add a Render **Cron Job** running
  `python -m app.ml.pipeline` (same repo/root/Docker, but as a Cron service) every few minutes so anything missed is re-scored. See [DEPLOYMENT.md](DEPLOYMENT.md) and [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).
- **Scaling:** the in-memory rate limiter is per-instance — keep a single web instance until you move it to Redis.

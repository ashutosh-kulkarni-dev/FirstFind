# ThriftFind — Production Readiness Review

_Date: 2026-08-15 · Scope: `app/backend` (FastAPI) + notes on `app/frontend` (React/Vite)_

This document (1) records the functionality verification that was run, and (2) lists the
concrete work required to take the app from a solid MVP to production-grade. Findings are
prioritized **P0 (blocker)** → **P1 (important)** → **P2 (polish)**.

> **Deployment pass (2026-08-15).** Target chosen: **frontend → Vercel, backend → Railway/Render,
> DB → Supabase (Postgres), source → GitHub.** See [DEPLOYMENT.md](DEPLOYMENT.md). Shipped in this
> pass: **P0-1** (JWT secret now hard-fails at startup when `ENVIRONMENT=production`), **P0-2**
> (`app/backend/Dockerfile` + `.dockerignore`, prod uvicorn bind `0.0.0.0:$PORT`), **P0-4** (root
> `.gitignore`), env-driven **CORS** + **`DATABASE_URL`** (Postgres driver added), and partial **P1-9**
> (GitHub Actions CI runs pyflakes + both smoke harnesses + a frontend build). Still open: **P0-3**
> (Alembic), **P1-1** (Redis rate limit), **P1-2** (cron the batch pipeline), **P1-3/4/5/6/7/8**, and
> the rest of P2.

---

## 1. Functionality verification — PASSED

Two headless end-to-end harnesses were run against the live stack (SQLite + live HuggingFace
Inference API + live Groq):

| Harness | Coverage | Result |
|---------|----------|--------|
| `app/backend/_audit.py` | Every endpoint + feature (auth, all store filters, areas/categories/nearby, detail, async review→sentiment, save, zones, recommendations, all 11 chat intents, timing header, rate-limit 429) | **40 / 40 passed** |
| `app/backend/_verify.py` | ML/retrieval invariants (visibility rules, view dedup, CF persistence + cold-serving, hard/soft filters, typo tolerance, zone clustering, batch pipeline) | **23 / 23 passed** |

**Everything works as designed.** The findings below are about hardening, not broken features.

One product observation surfaced during the audit: the seed dataset contains **no prices**, and
`GET /api/stores?price_max=…` treats price as a *hard* filter (excludes unpriced stores), so that
filter currently returns an empty list. See P1-7.

---

## 2. Priority findings

### P0 — Must fix before any public deployment

| # | Area | Finding | Recommendation |
|---|------|---------|----------------|
| P0-1 | Security | `JWT_SECRET` defaults to `"dev-secret-change-in-prod"` and startup only **warns** ([main.py `_startup_checks`](app/backend/app/main.py)). A deploy that forgets to set it ships a forgeable-token app. Also the key is short (JWT lib warns <32 bytes). | **Fail startup** (raise) if the secret is the default or <32 bytes, in any non-dev env. Generate a 32+ byte random secret. |
| P0-2 | Deployment | No production run path. `run.py` is dev-only (`reload=True`, binds `127.0.0.1`). No Dockerfile / Procfile / process manager. | Add a `Dockerfile` + run under `uvicorn`/`gunicorn` with multiple workers, bind `0.0.0.0`, `--no-reload`, env-driven. Add `.dockerignore`. |
| P0-3 | DB | No migrations. Schema is created with `create_all`, which **cannot alter existing tables**; schema changes require the destructive `seed()` (drop + recreate = data loss). The recent column removal already needed a manual reseed. | Adopt **Alembic**. Make `seed()` data-only (no `drop_all`) or clearly guard it as a dev-only reset. |
| P0-4 | Secrets/repo | `.env` lives in the backend dir; stray DB files (`thriftfind.db`, `_verify.db`, `_audit.db`) and a legacy `FIrstFInd/` duplicate tree sit in the repo. | Initialize git with a `.gitignore` covering `.env`, `*.db`, `__pycache__`, `node_modules`, `dist`. Remove the legacy `FIrstFInd/` dir and stray root files. `.env.example` is already present — good. |

### P1 — Important for a real launch

| # | Area | Finding | Recommendation |
|---|------|---------|----------------|
| P1-1 | Scaling | **Rate limiter is in-memory, per-process** ([middleware.py](app/backend/app/middleware.py)). With >1 worker each has its own window, so the effective limit multiplies and is bypassable. | Move to Redis (or a gateway/CDN rate limit). Add stricter throttling on `/auth/login` + `/auth/register` (brute-force / signup abuse). |
| P1-2 | Reliability | Sentiment scoring and recommender refit run as **in-process FastAPI `BackgroundTasks`** — no retry, no durability; lost if the worker restarts mid-task. | Sentiment already self-heals: the batch pipeline re-scores `sentiment IS NULL` rows — **schedule it on a cron** (every few min). Recommender refit has no such net beyond startup; either a periodic cron refit or a real task queue (RQ/Celery/Arq). |
| P1-3 | External dep | HF Inference API is now a hard external dependency: free-tier **quota/rate limits**, cold starts, latency. Current handling is a single attempt → VADER fallback (acceptable degradation) but no retry/backoff or monitoring. | Add one retry w/ short backoff before falling back; log fallback rate as a metric; for SLA, consider a dedicated HF Inference Endpoint. Document the token's quota. Same external-dep note applies to **Groq**. |
| P1-4 | Observability | `logging.basicConfig` INFO only; no structured logs, request IDs, error tracking, or metrics. | Structured JSON logging + request/correlation IDs; add **Sentry** (or similar) for exceptions; expose Prometheus metrics or use the platform's. |
| P1-5 | Health checks | `GET /api/health` is static (liveness only) — it returns `ok` even if the DB is down ([misc.py](app/backend/app/routers/misc.py)). | Add a **readiness** check that pings the DB (and optionally HF/Groq), separate from liveness, for orchestrator probes. |
| P1-6 | DB perf | Hot query paths lack indexes: `Store.area`, `Review.store_id`, and the `Interaction(user_id, store_id, kind, created_at)` dedup lookup ([stores.py `store_detail`](app/backend/app/routers/stores.py)). `Store.categories.contains()` is a `LIKE` scan. | Add indexes for the filter/join columns; a composite index for the interaction dedup query. Reconsider the category `LIKE` (a join table or JSON/GIN index) if the catalog grows. |
| P1-7 | Product/data | Dataset has **no prices**, so the `price_max` list filter is effectively dead, and price never contributes to ranking/zones. Also list-endpoint price filter is *hard* while the chatbot's is *soft* — inconsistent semantics. | Source price data (even coarse bands), or hide the price filter until available. Align the two price semantics deliberately. |
| P1-8 | Build reproducibility | `requirements.txt` uses unpinned `>=` — non-reproducible builds; a transitive bump can break prod. | Pin versions / add a lockfile (`pip-tools`, `uv`, or Poetry). Split dev-only deps (pyflakes, test tools) from runtime. |
| P1-9 | Testing/CI | Only smoke scripts (`_verify.py`, `_audit.py`) — no pytest suite, no CI gate. | Port both harnesses to **pytest** (they're already assertion-based), add unit tests for `utils`, `auth`, `recommender`, `zones`, `chatbot` retrieval. Wire CI (lint + type-check + tests) on push. |

### P2 — Polish / longer-term

| # | Area | Finding | Recommendation |
|---|------|---------|----------------|
| P2-1 | API design | No response schemas / OpenAPI response docs (endpoints return hand-built dicts), no API versioning, no pagination on `/api/stores` (returns all ~105 — unbounded as data grows). | Add `/api/v1` prefix; add `limit`/`offset` pagination; optionally reintroduce typed response models for the public contract. |
| P2-2 | Security headers | No HSTS / `X-Content-Type-Options` / `X-Frame-Options` / CSP. CORS origin list is dev-only localhost. | Add a security-headers middleware; make CORS origins env-driven with the real frontend domain. |
| P2-3 | Frontend | Calls relative `/api/...` ([api.js](app/frontend/src/api.js)) — relies on same-origin or a Vite dev proxy; token in `sessionStorage` (XSS-exposed). | Document deploy topology (static frontend behind the same origin / reverse proxy, or an env-configured API base URL). Consider httpOnly cookie auth if XSS surface grows. |
| P2-4 | Naming | "FirstFind" vs "ThriftFind" mixed across app title, health string, LLM prompt, `FIRSTFIND_JWT_SECRET`, DB name `firstfind`. | Unify to ThriftFind (env var + DB name are breaking — do during a planned config change). |
| P2-5 | Chat | `ChatIn.session_id` is accepted but unused — no conversation memory. | Either implement multi-turn context or drop the field to avoid implying support. |
| P2-6 | Tooling | No formatter/linter/type-checker config committed. | Add `ruff` + `mypy` (or `pyright`) configs; enforce in CI. |

---

## 3. What's already good (keep it)

- **Clean layered architecture** — `config / database / models / schemas / auth / middleware / utils / routers / ml`, no circular imports, no spaghetti.
- **Lean dependencies** — every package in `requirements.txt` is used; the heavy local model was removed in favour of the HF API.
- **ML off the request path** — the request path only reads precomputed results or does one cheap call; heavy work is in the batch pipeline / background tasks. Recommender results are persisted to the DB and **survive restarts / serve identically across workers** (`StoreSimilarity` / `UserRecommendation` tables with in-memory fallback).
- **Graceful degradation** — HF → VADER, Groq → rule-based chatbot; the app never hard-fails on an external outage.
- **Sensible data hygiene** — store visibility gated on coordinates, view-dedup to protect the CF signal, honest empty results (no off-constraint padding) in retrieval.
- **DB connection pooling** with `pool_pre_ping` + recycle already configured.

---

## 4. Suggested sequencing

1. **P0 block** (secret enforcement, Dockerfile + prod server, Alembic, repo/gitignore hygiene) — required before exposing anything publicly.
2. **P1 reliability/scaling** (Redis rate limit, cron for pipeline + recommender, HF retry+metrics, readiness probe, indexes, pinned deps, pytest+CI).
3. **P1-7 data** (prices) — product decision; unblocks a currently-dead filter.
4. **P2 polish** iteratively.

_Verification artifacts: `app/backend/_audit.py` (40 checks) and `app/backend/_verify.py` (23 checks). Both are dev-only and should be moved into a `tests/` package as part of P1-9._

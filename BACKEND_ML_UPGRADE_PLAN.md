# FirstFind — Backend & ML Upgrade Plan

## ✅ Implementation status (all phases done)

| Phase | Status | Notes |
|---|---|---|
| 0.1 MySQL local | ✅ Done | `DATABASE_URL` from `.env` (URL-encoded creds); pooled engine; VARCHAR lengths added for MySQL; seeds on first boot. |
| 1 ML off request path | ✅ Done | `ml/tasks.py` background CF refit (debounced; saves force). Single-review sentiment stays real-time inline. |
| 2 Multilingual sentiment | ✅ Done | `twitter-xlm-roberta` warm singleton, VADER fallback, `truststore`+`sentencepiece` for this env's SSL. |
| 3 Hybrid recommender | ✅ Done | CF ⊕ content similarity (α=0.6); cold stores now get neighbours. |
| 4 Batch pipeline | ✅ Done | `ml/pipeline.py` (sentiment→scores→zones→recommender). Run: `python -m app.ml.pipeline`. |
| 5 HDBSCAN zones | ✅ Done | Density clusters + noise-reattach; KMeans fallback. |
| 6 Groq chatbot | ✅ Done | LLM phrasing grounded in retrieved stores; rule-based fallback. Add `GROQ_API_KEY` to enable. |
| 7 Hardening | ✅ Code-level done | JWT-default warning + engine-status logs at boot. **Launch-time infra below still pending.** |

**Still pending (launch-time, owned by you):** Supabase/Postgres cutover + PostGIS for `nearby`;
Redis-backed rate limiting if running >1 worker; retiring `FIrstFInd/backend` once you're happy
the ported ideas (pipeline, Groq) live in FastAPI.

**Ops notes:** first server boot downloads ~1.1 GB sentiment weights (one-time) and warms the
model (~40 s) — subsequent boots load from cache. Schedule `python -m app.ml.pipeline` as a
cron (few min for scores, nightly for zones).

---

**Goal:** production-grade, real-time behaviour after launch — *without stripping out the ML*.
The ML (sentiment → quality scoring, personalized recommendations, geospatial zones,
conversational discovery) is the product's differentiator. This plan **keeps every ML
capability** and instead makes each one (a) more accurate on real Bengaluru/Hinglish data
and (b) safe to run under real traffic.

Guiding principle borrowed from the older `FIrstFInd` prototype and made explicit here:

> **The request path never trains a model. It only reads precomputed results or runs a
> single cheap inference. All heavy ML runs in the background.**

Canonical backend for this plan: **`app/backend` (FastAPI)**. The `FIrstFInd/backend`
(Django) prototype is retired, but two of its ideas are ported in (batch ML pipeline,
LLM chatbot).

---

## Decisions locked in (this revision)

| Phase | Decision |
|---|---|
| 1 | ML off request path — **yes**. Local DB → **MySQL now**, migrate to **Supabase (Postgres)** later. |
| 2 | Multilingual sentiment — **yes**, and the model **must be callable in real time** once launched (warm, fast inference), not batch-only. |
| 3 | Hybrid recommender — **yes, go.** |
| 4 | Batch ML pipeline — **yes** (confirmed good practice; see rationale in Phase 4). |
| 5 | HDBSCAN zones — **yes, go.** |
| 6 | LLM chatbot — **yes, using Groq** (the API already in use), not Claude. |
| 7 | Production hardening — **yes.** |

> **DB:** local dev uses **MySQL**. The eventual Supabase migration is owned by you and out
> of scope for this plan — we simply keep everything on the SQLAlchemy ORM with the
> connection string in one env var (`DATABASE_URL`), which keeps your migration clean.

---

## 0. Current state (verified)

| Model | File | Today | Runs where | Real-time risk |
|---|---|---|---|---|
| Sentiment | `app/backend/app/ml/sentiment.py` | VADER lexicon | inside `POST /reviews` | English-only; misses Hinglish |
| Recommender | `app/backend/app/ml/recommender.py` | item-item cosine CF | **refit on every view/save** | O(users×items²) in hot path |
| Zones | `app/backend/app/ml/zones.py` | KMeans k=4, rank-labelled | seed only | forces 4 zones even if unsupported |
| Chatbot | `app/backend/app/ml/chatbot.py` | rule-based regex | request path (fine) | breaks on paraphrase/typos |

Verified working: 48 stores / 284 reviews / 85 interactions / 4 zones seeded; all four models execute.

Two problems are **architectural, not model quality**, and must be fixed first:
1. `recommender.build(db)` is called synchronously inside `GET /stores/{id}` and `POST /save`.
2. Sentiment analysis runs synchronously inside `POST /reviews`.

Both put ML on the user's latency path. Under launch traffic + SQLite's single writer, this is the first thing that will fall over.

### 0.1 Local database → MySQL now (Supabase/Postgres later)
- Move local dev from SQLite to **MySQL** (Docker `mysql:8` or a local install), driver
  `PyMySQL` (or `mysqlclient`).
- Change **only** `DATABASE_URL` in `app/backend/app/config.py`
  (`mysql+pymysql://user:pass@localhost/firstfind`). SQLAlchemy models are unchanged.
- Keep everything ORM-level (no raw MySQL SQL) so the later Supabase/Postgres move is a
  driver + URL swap. See the DB caveat above.
- Note: MySQL is a real DB server with concurrent writes, so it *also* removes the SQLite
  single-writer bottleneck immediately — a bonus for real-time launch behaviour.

---

## Phase 1 — Get ML off the request path (do this first, no accuracy change)

**Why first:** it is the highest-risk, lowest-effort change and unblocks every model upgrade below. No model is removed; they just stop running *synchronously per request*.

### 1.1 Background the recommender refit
- Remove `recommender.build(db)` from `routers/stores.py` (`store_detail`, `save_store`).
- Replace with either:
  - **FastAPI `BackgroundTasks`** — enqueue a refit after the response is sent, debounced (refit at most once every N seconds), **or**
  - a **periodic refit** (APScheduler / a simple asyncio loop every 2–5 min).
- Add an incremental path: on a new interaction, update just that user's vector instead of a full matrix rebuild. Full refit stays as the periodic job.
- Cache the `id → index` map built in `fit()` so `similar_stores()` stops doing O(n) `list.index()`.

### 1.2 Background the sentiment scoring
- In `POST /reviews`: save the review with `sentiment = NULL` and return immediately.
- Score sentiment in a `BackgroundTask` (or the batch job in Phase 4), then recompute the store's `experience_score`.
- Frontend already tolerates a store score updating a beat later.

**Outcome:** review submit and store views become instant DB operations. ML still happens — just asynchronously.

---

## Phase 2 — Sentiment: VADER → multilingual transformer (biggest accuracy win)

Keep the model, upgrade the engine. VADER is an English social-media lexicon and is blind
to the actual review vocabulary (`bakwaas`, `mast`, `paisa vasool`, `chindi`, `sasta`).

### Recommended: local multilingual transformer
- Model: **`cardiffnlp/twitter-xlm-roberta-base-sentiment`** via `transformers` + `torch`.
  - Multilingual (handles Hinglish/Indian English far better), still small enough to self-host.
  - This is the RoBERTa the original SRS asked for.
- **Keep the exact interface** `analyze(text) -> (label, score)` so it's a drop-in for `sentiment.py`.
- Load the model **once at startup** (module singleton, same pattern as `_analyzer` today).

### Keep VADER as the offline fallback
- If the transformer fails to load (no GPU/low-RAM box), fall back to VADER automatically.
- This mirrors the `FIrstFInd` HF-API→lexicon fallback and guarantees the demo never dies.

### Real-time requirement (locked in)
The model **must be callable in real time** once the app is launched — not batch-only. Design for that:
- **Warm singleton:** load the model **once at startup** (module-level, same pattern as
  today's `_analyzer`). First inference pays the load cost; every call after is warm.
- **Fast inference:** `twitter-xlm-roberta-base` on CPU is ~tens of ms per short review —
  fast enough to call **synchronously in real time** when needed (e.g. live sentiment as a
  user types, or scoring a single review inline).
- **Two call modes, same model instance:**
  1. **Real-time** — call `analyze(text)` directly for single, interactive requests.
  2. **Background/batch** — the review-submit flow (Phase 1.2) and the pipeline (Phase 4)
     reuse the *same warm model* to score in bulk without blocking the user.
- **Keep it warm under load:** run the model in the API process (or a dedicated inference
  worker) so it never cold-starts on the request path. Pin CPU threads / batch size so one
  slow inference can't stall the event loop (offload to a threadpool via
  `run_in_executor` / `fastapi.concurrency.run_in_threadpool`).

**Alternative (if you don't want to ship model weights):** HF Inference API
(`twitter-roberta`). Trade-off: external network dependency + per-call latency/cost — usable
for real time only if the API is fast and reliable; the local warm model is the safer bet
for a launched, real-time product.

---

## Phase 3 — Recommender: keep CF, make it production-shaped

The item-item cosine CF is a legitimate MVP and **stays**. Upgrade it along two axes:
scale and cold-start.

### 3.1 Scale / correctness (pairs with Phase 1.1)
- Refit in the background, not per request (done in Phase 1).
- Optional: swap the hand-rolled numpy cosine for **`implicit` (ALS)** — purpose-built for
  implicit view/save/like feedback, faster and more accurate; this is the "SVD/Surprise"
  the SRS envisioned. Same `recommend_for_user` / `similar_stores` interface.

### 3.2 Cold-start (real launch reality: most users/stores have no history)
- Blend CF with **content-based similarity** (category, price band, zone, quality) — exactly
  what `FIrstFInd/run_pipeline.py` step 4 does. A hybrid beats either alone at launch scale.
- New user → content + top-rated fallback (already partially present).
- New store → content similarity until it accrues interactions.

**Outcome:** personalization survives day-one traffic when interaction data is sparse, and the CF "uniqueness" is retained and strengthened.

---

## Phase 4 — Introduce a batch ML pipeline (the `FIrstFInd` idea, ported to FastAPI)

Create one place where all heavy ML runs, so the web app only ever **reads** precomputed
values. This is the single most important production pattern.

> **Is this good practice / will it work well? Yes.** Separating "training/bulk scoring"
> (batch) from "serving" (read precomputed) is the standard production ML architecture — it
> keeps user requests fast and predictable, makes ML failures non-fatal to the app, and lets
> you re-run/scale ML independently. It works especially well here because your data changes
> slowly (stores, reviews, zones) so precomputed results stay fresh for minutes-to-hours.
> The `FIrstFInd` prototype already proved the pattern; this just ports it to FastAPI. The
> only nuance: the two genuinely interactive models — **sentiment (Phase 2, real-time
> callable)** and **chatbot (Phase 6)** — are allowed to run live; everything else is batch.

- New module: `app/backend/app/ml/pipeline.py` + a CLI entry (`python -m app.ml.pipeline`)
  or a FastAPI admin endpoint, runnable as a **cron / scheduled task**.
- Stages (mirrors the proven `run_pipeline.py`):
  1. Sentiment on unscored reviews (Phase 2 model).
  2. Recompute each store's `experience_score`.
  3. Recompute zones (Phase 5).
  4. Refit recommender + write similar-store lists.
- Frequency: every few minutes for sentiment/scores (near-real-time feel), nightly for zones.
- The in-request `BackgroundTask` from Phase 1 handles the "instant feedback" cases;
  the pipeline handles bulk correctness and consistency.

**Real-time perception:** users see their review/save reflected immediately (background task),
and the fuller ML recompute catches up within minutes — no user ever waits on a model.

---

## Phase 5 — Zones: KMeans → HDBSCAN (honest clusters)

Keep zones as a headline feature; improve the clustering.
- Current KMeans forces exactly 4 clusters and rank-labels them, inventing a "Hidden Gem"
  even when the data doesn't support one.
- Switch to **HDBSCAN** (density-based, no fixed k, honest outliers) — already used in
  `FIrstFInd/run_pipeline.py`. Label clusters post-hoc by price/score/review stats.
- Runs in the nightly pipeline (Phase 4), never in the request path.
- **If** the UI genuinely requires exactly-4 labelled quadrants, keep KMeans but document it
  as a product constraint, not a data-driven result.

---

## Phase 6 — Chatbot: LLM intent + retrieval + rule fallback (biggest UX win)

Keep the rule-based engine — it becomes the **offline fallback**, not the primary path.
Adopt the `FIrstFInd` two-call pattern, upgraded:

1. **Call 1 — intent extraction → JSON** `{area, category, price, min_quality, query_type}`.
2. **Retrieval** — your own DB does the exact, free lookup (no hallucinated stores).
3. **Call 2 — phrasing** the retrieved results conversationally.
4. **Fallback** — if no API key / call fails, the existing `chatbot.py` rule engine answers.

- **Provider: Groq** (the API already in use). Reuse the exact pattern already written in
  `FIrstFInd/backend/core/chatbot.py` (`_groq()` two-call flow, `response_format` JSON mode)
  — port it into `app/backend/app/ml/chatbot.py` as the primary path, keeping the existing
  FastAPI rule engine as the offline fallback. Config: `GROQ_API_KEY`, `GROQ_MODEL` in env
  (e.g. a fast Llama/Mixtral chat model on Groq).
- **Real-time:** this is the one ML call that legitimately lives in the request path
  (it's the chat feature itself). Groq is very low-latency; still set a hard timeout (~20s
  as in the prototype) and fall back to the rule engine on any failure so chat never hangs.

**Outcome:** natural-language robustness (paraphrase, typos, multi-intent) while retrieval
stays grounded in your DB and the app still works fully offline.

---

## Phase 7 — Production hardening (independent of models)

- **`JWT_SECRET`**: inject from env; the `"dev-secret-change-in-prod"` default must not ship.
- **Database**: **MySQL locally now** (Phase 0.1) → **Supabase (Postgres)** at launch. Both
  give concurrent writes over today's SQLite. On Supabase you additionally get **PostGIS**
  for `nearby`/`haversine` (today a full-table Python scan in `routers/stores.py`). Keep the
  ORM dialect-clean (per the caveat at the top) so the switch stays a driver + URL change.
- **Rate limiting**: current in-memory `RateLimitMiddleware` is per-process; move to Redis if
  running >1 worker.
- **Observability**: keep `TimingMiddleware`; add structured logs + error tracking around the
  ML pipeline and the Claude calls.
- **Retire `FIrstFInd/backend`** once its two ideas (pipeline + LLM chatbot) are ported, to
  stop the two codebases from drifting.

---

## Sequencing & effort

| Phase | What | Risk | Effort | Ships |
|---|---|---|---|---|
| 1 | ML off request path | Low | S | first |
| 2 | Multilingual sentiment | Low | S–M | with 4 |
| 4 | Batch pipeline | Low | M | early |
| 3 | Hybrid CF (+ optional ALS) | Med | M | after 4 |
| 6 | LLM chatbot (Groq) + rule fallback | Med | M | parallel |
| 5 | HDBSCAN zones | Low | S | with 4 |
| 7 | MySQL→Supabase / secrets / infra | Med | M | before public launch |

> Note: local DB moves to **MySQL** in Phase 0.1 (early, unblocks concurrent writes);
> the **Supabase/Postgres** cutover is the Phase 7 launch step.

**Nothing here removes an ML capability.** Every model is retained; each is either made more
accurate on real data (sentiment, chatbot), more honest (zones), or more scalable
(recommender) — and all heavy computation moves off the user's latency path so the ML that
makes FirstFind unique can actually run in real time at launch.

---

## Fast, safe first steps (low-risk, high-leverage)

1. **Phase 1** — background the recommender refit + sentiment scoring (pure architecture, no accuracy change).
2. **Phase 2** — drop the multilingual sentiment model behind the existing `analyze()` interface, VADER as fallback.
3. **Phase 6** — port the existing Groq intent+phrasing chatbot into FastAPI, with the current rule engine as fallback.

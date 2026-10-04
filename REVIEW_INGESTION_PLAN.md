# Review Ingestion & AI Score — Plan

> Ingest current, real-world reviews for each store (keyed by name + location),
> compute the AI score, and refresh it **weekly** without ever hitting an API limit.

**Decisions locked in (2026-08-31):**
- **Store list / input:** [`data/stores.csv`](data/stores.csv) — 131 Bengaluru stores, each with `name`, `locality_raw`, `city`, `lat`, `lng`, `instagram`, `phone`. No review data or place IDs today.
- **Review source:** Google Places API (resolves reviews from just `name` + `locality` + `lat/lng`, which is all `stores.csv` gives us). Outscraper/SerpAPI is a drop-in alternative if we later want *all* reviews instead of Google's top ~5. See §7.
- **AI score method:** **unchanged** — reuse the existing 70% avg star rating + 30% HF sentiment blend in [`experience_score()`](app/backend/app/ml/sentiment.py#L113). No new scoring math.
- **Automation:** **weekly** GitHub Actions cron, mirroring [`metro-refresh.yml`](.github/workflows/metro-refresh.yml).

---

## 1. Goal & non-goals

**Goal:** Each week, for every store in `stores.csv`, fetch its current external reviews, run sentiment, and recompute `Store.experience_score` + `Store.review_count` so the map/score pills reflect real sentiment rather than only app-user reviews.

**Non-goals:** No change to the scoring formula, the zones clusterer, the recommender, or the serving path. This plan only *adds a data source* upstream of the existing ML batch.

---

## 2. Where this slots into the current system

Today reviews only accrue when app users post them ([`seed.py:8`](app/backend/app/seed.py#L8)). The scoring batch already exists and already does exactly what we need **once reviews are in the `reviews` table**:

- [`pipeline.py`](app/backend/app/ml/pipeline.py) → `score_pending_sentiment()` (sentiment on `sentiment IS NULL`) → `recompute_store_scores()` (the 70/30 blend).

So the **only new component** is an ingester that writes external reviews into the `reviews` table. Then we call the existing pipeline. Nothing downstream changes.

```
stores.csv ──► resolve place_id ──► fetch reviews ──► upsert Review rows ──► run_pipeline()
              (Google Find Place)   (Google Details)   (dedupe/idempotent)   (sentiment + score)
```

---

## 3. New / changed components

### 3.1 New module — `app/backend/app/ml/ingest_reviews.py`
Pure ingestion; no scoring logic (scoring stays in `sentiment.py`).

- `resolve_place_id(store) -> str | None` — Google **Find Place From Text**, query = `"{name} {locality_raw} {city}"`, `locationbias=circle:200@{lat},{lng}`. Returns the Google `place_id`. Cached (see 3.2) so we call this **once per store, ever**.
- `fetch_reviews(place_id) -> list[dict]` — Google **Place Details** with `fields=reviews,rating,user_ratings_total`. Returns Google's reviews (author, rating, text, time, review id).
- `ingest_store(db, store) -> int` — resolve → fetch → upsert; returns # new reviews.
- `ingest_all(db, limit=None) -> dict` — iterate stores, throttle, aggregate a summary. Never raises per-store; logs and continues (one bad store must not abort the run).

### 3.2 Data-model additions ([`models.py`](app/backend/app/models.py))
Minimal, additive columns (SQLite dev + Postgres prod — nullable, no destructive migration):

- **`Store.google_place_id`** `String(120) nullable` — cache the resolved place id so we skip Find Place on every subsequent run (this is the biggest quota saver, see §5).
- **`Store.external_rating`** `Float nullable` + **`Store.external_rating_count`** `Integer nullable` — Google's own aggregate, handy for display/QA (optional).
- **`Review.source`** `String(20) default "app"` — `"app"` | `"google"`. Lets us distinguish/re-fetch ingested rows.
- **`Review.external_id`** `String(128) nullable` — Google review id (or a stable hash of author+time). Powers idempotent upsert.
- **Unique constraint** `(store_id, source, external_id)` — dedupe guard so re-runs never duplicate a review.

### 3.3 A system user for ingested reviews
`Review.user_id` is NOT NULL. Seed one bot account (e.g. `reviews-bot@thriftfind.local`, `auth_provider="system"`) and attribute all ingested reviews to it. One-time addition to [`seed.py`](app/backend/app/seed.py).

### 3.4 Google ToS note (important)
Google's terms discourage long-term storage of raw review *text*. Two compliant options — pick one during build:
- **(a)** Store text only transiently: fetch → score sentiment in-memory → persist **only** the derived `sentiment`, `sentiment_score`, and `rating` (drop the text). The 70/30 blend needs only rating + sentiment_score, so scores are unaffected.
- **(b)** Store text but refresh/expire weekly (this run overwrites last week's). Simpler; acceptable for an internal analytics use.

Recommend **(a)** — it keeps us clean and the score identical.

---

## 4. AI score calculation — **unchanged**

The "AI score" is the existing blended `experience_score` (0–5), surfaced by the score pill/ring in the UI:

```
avg_rating  = mean(review.rating)                      # 1..5, from external reviews
avg_sent    = mean(review.sentiment_score)             # -1..1, from HF model
sent_stars  = (avg_sent + 1)/2 * 4 + 1                 # map -1..1 → 1..5
experience_score = round(0.7*avg_rating + 0.3*sent_stars, 2)
```

- **Sentiment engine:** HuggingFace Inference API, `cardiffnlp/twitter-xlm-roberta-base-sentiment` (Hinglish-aware), with VADER fallback — already implemented in [`sentiment.py`](app/backend/app/ml/sentiment.py). No change.
- After ingestion we simply call the existing `score_pending_sentiment()` + `recompute_store_scores()`.

---

## 5. "API key must not hit limits" — quota strategy

Two keys are in play: **Google Places** (fetch) and **HuggingFace** (sentiment).

### Google Places
- **Call budget:** 131 stores × (1 Find Place + 1 Details) = **262 calls** on the *first* run. After caching `google_place_id`, every later week is **131 calls** (Details only). Google's free monthly credit covers this many times over — but we still harden:
  - **Cache `place_id`** in `Store.google_place_id` → skip Find Place forever after run 1 (halves calls, and Find Place is the pricier SKU).
  - **Field mask** on Place Details (`fields=reviews,rating,user_ratings_total`) → billed on the cheapest SKU tier, not full Place Details.
  - **`MAX_CALLS_PER_RUN`** env guard (default e.g. 300) — hard stop so a bug can't loop into the paid tier.
  - **Throttle:** `time.sleep(MIN_INTERVAL)` between calls (≈100–200 ms) → stays well under QPS limits.
  - **Backoff:** on HTTP 429/`OVER_QUERY_LIMIT`, exponential backoff then abort gracefully with a partial-success summary (rest resumes next week).
  - **Resumability:** ingest in `id` order; because upserts are idempotent, a mid-run abort just continues next run.

### HuggingFace
- Already only scores `sentiment IS NULL` (no re-work), already batched off the request path, already falls back to VADER on failure. We add:
  - Small `sleep` between calls and a per-run cap so a weekly flood of new reviews can't spike the HF quota.
  - Warmup ping (exists) to avoid cold-start timeouts.

### Config (env) — added to [`config.py`](app/backend/app/config.py)
```
GOOGLE_PLACES_API_KEY   = ...            # new
INGEST_MAX_CALLS        = 300            # hard cap per run
INGEST_MIN_INTERVAL_MS  = 150            # throttle
INGEST_STORE_TEXT       = false          # ToS option (a)=false / (b)=true
# HUGGINGFACE_TOKEN already exists
```

---

## 6. Weekly automation (GitHub Actions)

New workflow `.github/workflows/reviews-refresh.yml`, modeled on `metro-refresh.yml`:

```yaml
name: Refresh Store Reviews & AI Score
on:
  schedule:
    - cron: '0 4 * * 1'      # Mondays 04:00 UTC (after metro-refresh at 03:00)
  workflow_dispatch:
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r app/backend/requirements.txt
      - name: Ingest reviews + recompute scores
        env:
          DATABASE_URL:           ${{ secrets.DATABASE_URL }}
          GOOGLE_PLACES_API_KEY:  ${{ secrets.GOOGLE_PLACES_API_KEY }}
          HUGGINGFACE_TOKEN:      ${{ secrets.HUGGINGFACE_TOKEN }}
        run: python -m app.ml.ingest_reviews --run-pipeline
```

- **Writes straight to the prod DB** (Supabase Postgres) via `DATABASE_URL` — same ORM, no code path difference. (Alternative: POST to a protected admin endpoint if we don't want CI to hold DB creds.)
- **Secrets** stored in GitHub repo settings — never committed.
- `workflow_dispatch` lets us trigger a manual run anytime.
- Entry point `python -m app.ml.ingest_reviews --run-pipeline` = `ingest_all()` then `run_pipeline()`.

---

## 7. Alternative review source (documented, not chosen)
If Google's ~5-review cap proves too thin for a meaningful score, swap `fetch_reviews()` for **Outscraper** (returns full Google Maps review history, storable). Same interface, same downstream — only the fetch function and the API key change. Keep this behind an `INGEST_PROVIDER=google|outscraper` flag so the switch is one env var.

---

## 8. Build order (checklist)
1. Add columns/constraint to `models.py` + a lightweight migration (dev DB is SQLite — recreate; prod Postgres — `ALTER TABLE ADD COLUMN`).
2. Add config vars to `config.py`; add secrets to GitHub + local `.env`.
3. Seed the reviews-bot system user.
4. Build `ingest_reviews.py` (resolve → fetch → upsert), with throttle/backoff/cap.
5. Wire `--run-pipeline` to call existing `run_pipeline()`.
6. Local dry-run against 3–5 stores (`--limit 5`), verify scores populate.
7. Add `reviews-refresh.yml`, test via `workflow_dispatch`.
8. Enable weekly schedule.

## 9. Validation & rollback
- **Validation:** after a run, assert `review_count > 0` for a healthy fraction of stores and `experience_score` in [1,5]; log per-store call counts to confirm we stayed under `INGEST_MAX_CALLS`.
- **Rollback:** ingestion is additive + idempotent. To undo, delete `reviews WHERE source='google'` and re-run `recompute_store_scores()`. `google_place_id` cache can stay.

## 10. Open questions for you
- **ToS option (a) drop text vs (b) store text** — which do you prefer? (Recommend (a).)
- Confirm the prod DB is reachable from GitHub Actions (Supabase network allowlist), or should CI hit an admin endpoint instead?
- Is Google's top-~5 reviews enough per store, or should we budget for Outscraper (full history)?

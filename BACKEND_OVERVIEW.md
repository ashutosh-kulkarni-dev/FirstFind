# ThriftFind — Backend Overview

A component-by-component explanation of how the ThriftFind backend works: the
overall objective of the app, and the objective of every piece of the backend.

Canonical backend: **`app/backend`** (FastAPI + SQLAlchemy). Everything below
refers to files under [app/backend/app/](app/backend/app/).

---

## 1. What the app is

**ThriftFind** helps people discover second-hand / thrift clothing stores in
**Bengaluru**. It is a curated, data-driven directory with four ML-powered
differentiators layered on top of a plain store listing:

| Capability | What the user gets |
|---|---|
| **Quality scoring** | Each store has an *experience score* (0–5) blended from real star ratings and the sentiment of its reviews — so ranking reflects how people actually felt, not just stars. |
| **Personalized recommendations** | A hybrid recommender learns from what each user views/saves/likes and suggests stores they'll probably like; new users/stores are covered by content similarity. |
| **Geospatial zones** | Stores are clustered on the map into labelled thrift zones (Budget / Premium / Hidden Gem / Mixed) so users can explore by neighbourhood character. |
| **Conversational discovery** | A chatbot answers natural-language questions ("vintage stores under ₹500 in Koramangala") by detecting intent, querying the DB, and (optionally) phrasing the reply with an LLM. |

### The one architectural rule

> **The request path never trains a model. It only reads precomputed results or
> runs a single cheap inference. All heavy ML runs in the background.**

This is the principle every backend decision follows. Store views and saves are
instant DB reads/writes; the expensive recommender refit happens *after* the
response is sent. Bulk ML (scoring all reviews, reclustering zones) runs in a
separate batch pipeline. Only two ML calls are allowed to run live: **single
review sentiment** and the **chatbot** — both are fast, single inferences.

---

## 2. Technology stack

| Concern | Choice | File |
|---|---|---|
| Web framework | FastAPI (ASGI, run via Uvicorn) | [main.py](app/backend/app/main.py), [run.py](app/backend/run.py) |
| ORM / DB access | SQLAlchemy 2.0 | [database.py](app/backend/app/database.py), [models.py](app/backend/app/models.py) |
| Database | MySQL locally (`pymysql`); Supabase/Postgres planned for launch | [config.py](app/backend/app/config.py) |
| Auth | JWT (PyJWT) + PBKDF2-SHA256 password hashing | [auth.py](app/backend/app/auth.py) |
| Sentiment | `cardiffnlp/twitter-xlm-roberta-base-sentiment` (transformers/torch), VADER fallback | [ml/sentiment.py](app/backend/app/ml/sentiment.py) |
| Recommender | Hybrid item-item cosine CF ⊕ content similarity (numpy) | [ml/recommender.py](app/backend/app/ml/recommender.py) |
| Zones | HDBSCAN with KMeans fallback (scikit-learn) | [ml/zones.py](app/backend/app/ml/zones.py) |
| Chatbot | Rule-based intent engine + optional Groq LLM phrasing | [ml/chatbot.py](app/backend/app/ml/chatbot.py), [ml/llm.py](app/backend/app/ml/llm.py) |

---

## 3. Request/data flow at a glance

```
                       ┌─────────────── FastAPI (main.py) ───────────────┐
  HTTP request ──▶ CORS ──▶ RateLimit ──▶ Timing ──▶ Router ──▶ get_db() │
                       │                                    │            │
                       │                        ┌───────────┴─────────┐  │
                       │                        ▼                     ▼  │
                       │                  SQLAlchemy ORM        ML modules│
                       │                   (models.py)          (ml/*.py) │
                       └──────────────────────┬──────────────────────────┘
                                              ▼
                                          MySQL DB
                                              ▲
   Background:  BackgroundTasks (recommender refit)  +  batch pipeline (cron)
```

---

## 4. Application core

### 4.1 `main.py` — application entry point
Builds the FastAPI app and wires everything together.
- **Lifespan startup** (`lifespan`): creates tables, seeds the DB if empty,
  fits the recommender once, and **warms the sentiment transformer** so the
  first real request doesn't pay the ~40s model-load cost. Also runs
  `_startup_checks()` which warns if `JWT_SECRET` is still the insecure default
  and logs whether the Groq chatbot is enabled.
- **`_db_empty()`**: decides whether to seed. Checks stores **and** reviews
  **and** zones (not just stores) so a half-finished seed self-heals instead of
  looking "seeded" forever.
- **Middleware order**: Timing → RateLimit → CORS.
- **Routers registered**: `auth_routes`, `stores`, `misc`.

### 4.2 `config.py` — configuration
Central config loaded from environment / `.env`.
- Builds `DATABASE_URL` (full URL, or assembled from `DB_*` parts;
  `quote_plus` protects special chars in the password).
- Holds `JWT_SECRET`, JWT algorithm/expiry, `GROQ_API_KEY` / `GROQ_MODEL`,
  `CORS_ORIGINS`, and constants (`CITY_CENTER` = Bengaluru, `N_ZONES`, `SEED`).
- Injects the OS trust store (`truststore`) so HuggingFace model downloads work
  behind corporate/AV SSL interception.

### 4.3 `database.py` — DB engine & sessions
- Creates the SQLAlchemy `engine` (SQLite gets `check_same_thread=False`;
  MySQL/Postgres get connection pooling with `pool_pre_ping` + `pool_recycle`
  so stale connections are recycled).
- `SessionLocal` session factory, `Base` for models, and `get_db()` — the
  FastAPI dependency that yields a request-scoped session and always closes it.

### 4.4 `middleware.py` — cross-cutting request handling
- **`TimingMiddleware`**: logs every request with latency and adds an
  `X-Response-Time` header (observability).
- **`RateLimitMiddleware`**: naive in-memory sliding-window limiter per client
  IP (default 120 req / 60 s → HTTP 429). MVP-grade; move to Redis when running
  more than one worker.

### 4.5 `auth.py` — authentication
- `hash_password` / `verify_password`: PBKDF2-HMAC-SHA256 with a random 16-byte
  salt, 120,000 iterations, stored as `salt:hash`.
- `create_token` / `_decode`: issue and verify JWTs.
- **Dependencies**: `get_current_user` (401 if missing — required auth) and
  `get_optional_user` (returns `None` for guests — used where login is
  optional, e.g. store detail and recommendations).

### 4.6 `utils.py` — shared helpers
- `haversine_km`: great-circle distance for the `nearby` endpoint and distance
  labels.
- `is_open_now`: evaluates opening hours **in IST** (Bengaluru), respecting
  `closed_days`; returns `None` when timing data is unknown.
- `store_to_dict`: the single serializer that turns a `Store` ORM object into
  the API JSON shape (splits comma-separated fields, rounds the score, computes
  `is_open_now` and optional `distance_km`).

---

## 5. Data model — `models.py`

Five tables. ML-derived columns are marked.

| Model | Purpose | Key / ML columns |
|---|---|---|
| **User** | Accounts (real, synthetic demo, and imported Google-Maps reviewers) | `email` (unique), `password_hash`, `is_synthetic` |
| **Store** | A thrift store | `id` (`blr-0001`), location, hours, `categories`/`closed_days` (comma-separated), price band. **ML:** `experience_score`, `review_count`, `zone_id` |
| **Review** | A rating + text for a store | `rating` (1–5), `text`. **ML:** `sentiment`, `sentiment_score` |
| **Interaction** | Implicit feedback for the recommender | `kind` = view / save / like |
| **Zone** | A geospatial cluster of stores | `label`, centroid, `store_count`, `avg_score`, `avg_price`, `description` |

`schemas.py` holds the Pydantic request/response models (`RegisterIn`,
`StoreOut`, `StoreDetailOut`, `ReviewIn`, `ZoneOut`, `ChatIn`, `ChatOut`, …) —
the validated boundary between HTTP JSON and the ORM.

---

## 6. HTTP API — routers

### 6.1 `routers/auth_routes.py` — `/api/auth`
- `POST /register` — create account (409 if email taken), returns a JWT.
- `POST /login` — verify credentials, returns a JWT.

### 6.2 `routers/stores.py` — `/api/stores`
The core browsing surface.
- `GET ""` — list/filter stores by `area`, `category`, `price_max`, `open_now`,
  free-text `q`; sorted by experience score.
- `GET /areas` — distinct area names (for filter dropdowns).
- `GET /nearby?lat&lng&radius_km` — haversine distance scan, sorted by nearest.
  *(Currently a full-table Python scan; PostGIS is the planned upgrade.)*
- `GET /{store_id}` — store detail: reviews, a sentiment summary
  (positive/neutral/negative counts), and similar stores from the recommender.
  If the caller is logged in, it **logs a `view` interaction** and schedules a
  **debounced background recommender refit** — the refit never runs inline.
- `POST /{store_id}/reviews` *(auth)* — add a review. Sentiment is scored
  **inline** here (single cheap inference, allowed on the request path), then
  the store's `experience_score`/`review_count` are recomputed.
- `POST /{store_id}/save` *(auth)* — record a `save` interaction and trigger a
  **forced** background refit (a save is a strong signal, so it skips the
  debounce but still runs off the request path).

### 6.3 `routers/misc.py` — `/api`
- `GET /health` — liveness probe.
- `GET /zones` — all zones, each with its top-3 stores.
- `GET /recommendations` — personalized picks for a logged-in user; falls back
  to top-rated stores for guests / cold-start.
- `POST /chat` — natural-language discovery (delegates to the chatbot).

---

## 7. Machine-learning modules — `app/ml/`

### 7.1 `sentiment.py` — review sentiment → quality signal
- Primary engine: **`twitter-xlm-roberta-base-sentiment`**, a multilingual
  transformer that understands Hinglish/Indian-English thrift vocabulary
  ("bakwaas", "mast", "paisa vasool", "sasta") that VADER's English lexicon
  misses.
- Loaded once as a **thread-safe warm singleton** (`_get_pipe`, `warmup`) so
  `analyze()` is real-time callable; **VADER is the automatic fallback** if
  torch/transformers/weights are unavailable, so the app never hard-fails.
- `analyze(text) -> (label, compound∈[-1,1])` — stable interface used inline,
  in the batch pipeline, and by the seeder.
- `experience_score(reviews)` — blends **70% average star rating + 30%
  sentiment** into the 0–5 store score.

### 7.2 `recommender.py` — hybrid personalization
- Item-item **cosine collaborative filtering** over implicit feedback
  (view=1, save=2, like=3) **blended** with **content similarity** built from
  store attributes (categories, price band, zone, quality):
  `sim = α·CF + (1−α)·content`, α=0.6.
- The content half means **cold stores still get neighbours** and **sparse
  users still get sensible picks** — CF alone cold-starts badly at launch.
- Public interface: `build(db)` (refit), `recommend_for_user(user_id)`,
  `similar_stores(store_id)`. A module-level singleton `recommender` is fit at
  startup and rebuilt only in the background.

### 7.3 `zones.py` — geospatial clustering
- **HDBSCAN** over (lat, lng): finds however many clusters the data supports,
  no forced count. Two product adjustments: **noise points are reattached** to
  the nearest cluster (so every store shows on the map), and if density
  clustering can't find ≥2 clusters it **falls back to KMeans(N_ZONES)**.
- Clusters are labelled by rank into the four archetypes — **Premium** (highest
  avg price), **Budget** (lowest), **Hidden Gem** (fewest reviews), **Mixed**
  (rest) — each with a human-readable description.

### 7.4 `chatbot.py` — conversational discovery (rule engine)
- Detects one of ten intents (find_by_area / _category / _price, open_now,
  zone_exploration, store_recommendation, review_insight, store_comparison,
  best_time_to_visit, general_assistance) via regex + category synonyms.
- Extracts entities (area, category, price, store names) with fuzzy matching
  (`difflib`) so typos/paraphrases still resolve.
- Retrieves the **exact** answer from the DB (no hallucinated stores) and
  composes a reply plus store cards. This is the offline-safe backbone.

### 7.5 `llm.py` — optional Groq phrasing (Phase 6)
- When `GROQ_API_KEY` is set, `phrase_reply()` sends the rule engine's draft +
  the retrieved stores to Groq, which **rephrases conversationally, grounded
  strictly in the stores we actually retrieved** (told never to invent stores).
- Any failure (no key, timeout, HTTP error) returns the rule-based draft
  unchanged — so chat is never broken by the LLM. Retrieval always stays in our
  DB; the LLM only affects wording.

### 7.6 `tasks.py` — background refit (Phase 1)
- `refit_recommender(force=False)`: rebuilds the CF model off the request path
  via FastAPI `BackgroundTasks`. **Debounced** (at most one rebuild per 15 s)
  for rapid views; `force=True` (used by save) skips the debounce. Opens its
  own DB session because the request session is already closed by then.

### 7.7 `pipeline.py` — batch ML pipeline (Phase 4)
The one place heavy ML runs; the web app only ever *reads* what it computes.
Run as a cron (`python -m app.ml.pipeline`). Stages, in order:
1. **Score pending sentiment** — reviews where `sentiment IS NULL`.
2. **Recompute store scores** — `experience_score` + `review_count` per store.
3. **Recompute zones** — recluster, rewrite the `Zone` table, reassign
   `store.zone_id` (before the recommender, since `zone_id` feeds content
   features).
4. **Refit the recommender**.

All stages run in one transaction (rollback on failure). Suggested cadence:
every few minutes for sentiment/scores, nightly for zones.

---

## 8. Database seeding — `seed.py`

Bootstraps a realistic dataset from real source files, atomically (one
transaction — a killed seed leaves the DB unchanged rather than half-populated).

1. **Stores** from [data/stores.json](data/) — real names, coordinates, timings.
   Localities are canonicalised (`canonical_area`) into clean area names,
   missing coordinates are backfilled from same-area centroids, implausible
   `00:00` opening times are nulled, and synthetic enrichment
   (categories, price bands) is added and flagged.
2. **Users** — synthetic demo accounts **plus** real Google-Maps reviewer
   accounts imported from `googlemaps_reviews.csv` (relative dates like
   "3 weeks ago" are parsed to timestamps).
3. **Reviews** — real Google-Maps reviews first; synthetic template reviews are
   generated only for stores that have no real reviews, so every store has ML
   content.
4. **ML pass** — sentiment + experience scores, then geospatial zones.
5. **Interactions** — synthetic view/save/like events so collaborative
   filtering has signal on day one.

---

## 9. Running the backend

```bash
# from app/backend
pip install -r requirements.txt          # torch/transformers pull ~1.1 GB weights once
python -m app.seed                        # optional: seed DB (auto-runs on first boot if empty)
python run.py                             # dev server on http://127.0.0.1:8000
python -m app.ml.pipeline                 # run the batch ML pipeline (schedule as cron)
```

Key environment variables (`app/backend/.env`): `DATABASE_URL` (or `DB_*`),
`FIRSTFIND_JWT_SECRET`, `GROQ_API_KEY`, `GROQ_MODEL`.

**Boot cost:** the first server start downloads ~1.1 GB of sentiment weights and
warms the model (~40 s); subsequent boots load from cache.

---

## 10. How the ML principle shows up in each request

| User action | On the request path | In the background |
|---|---|---|
| View a store | read store + reviews + `similar_stores()` (precomputed matrix) | debounced recommender refit |
| Save a store | write one `Interaction` row | forced recommender refit |
| Submit a review | one sentiment inference + score recompute *(cheap, allowed)* | picked up by pipeline for consistency |
| Ask the chatbot | intent detect + DB retrieval + optional Groq phrasing *(the feature itself)* | — |
| Browse / zones / recs | pure DB reads of precomputed scores, zones, recs | batch pipeline keeps them fresh |

Nothing a user does ever triggers model *training* inline — that is the design
guarantee that keeps ThriftFind fast under real traffic while still shipping all
four ML features.

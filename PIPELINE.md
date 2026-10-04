# ThriftFind — Project Pipeline

> End-to-end data & ML pipeline: how raw store/review data becomes the scores,
> zones, recommendations, and chat answers the app serves. Written to accompany
> [`REVIEW_INGESTION_PLAN.md`](REVIEW_INGESTION_PLAN.md).

## Design principle
**Heavy ML runs in batch; the web app only ever *reads* precomputed results.**
No user request triggers a model refit or a network round-trip to an ML API on
its latency path. See [`pipeline.py`](app/backend/app/ml/pipeline.py) header.

---

## The pipeline, stage by stage

```
┌─ SOURCE DATA ─────────────────────────────────────────────────────────────┐
│ data/stores.csv / stores.json   131 BLR stores (name, locality, lat/lng…)  │
│ data/metro_stations_blr.json    Namma Metro stations (weekly OSM refresh)  │
│ data/geocode_cache.json         cached Nominatim pins                      │
└───────────────────────────────────────────────────────────────────────────┘
                                   │  seed.py
                                   ▼
┌─ RELATIONAL STORE (SQLAlchemy ORM) ───────────────────────────────────────┐
│ stores · reviews · users · interactions · zones · saved_lists ·            │
│ conversations · store_similarity · user_recommendations                    │
│ Local: MySQL/SQLite   Prod: Supabase (Postgres)                            │
└───────────────────────────────────────────────────────────────────────────┘
        ▲                                   │
        │ writes                            │ reads
        │                                   ▼
┌─ BATCH ML (app/ml/pipeline.py) ───┐   ┌─ SERVING (FastAPI, read-only ML) ──┐
│ 0. INGEST reviews  [NEW, weekly]  │   │ routers/: stores, clusters, metro, │
│    ingest_reviews.py              │   │   lists, conversations, auth, misc │
│      Google Places → reviews tbl  │   │ Returns precomputed scores/zones/  │
│ 1. SENTIMENT  sentiment IS NULL   │   │   recs; single-review sentiment &  │
│    HF Inference API (Hinglish)    │   │   chatbot are the only live ML.    │
│ 2. STORE SCORE  experience_score  │   └────────────────────────────────────┘
│      = 0.7·avg_rating +0.3·sent   │                    │
│ 3. ZONES  KMeans geo-cluster      │                    ▼
│      rewrite zones table          │   ┌─ FRONTEND (React + Leaflet) ───────┐
│ 4. RECOMMENDER  hybrid CF+content │   │ MapExplorer, StoreCard, ScoreRing, │
│      write store_similarity +     │   │ ChatWidget, Explore/Lists/Detail   │
│      user_recommendations         │   └────────────────────────────────────┘
└───────────────────────────────────┘
```

### Stage 0 — Review ingestion *(new; see REVIEW_INGESTION_PLAN.md)*
Weekly, resolves each store in `stores.csv` to a Google place and pulls current
reviews into the `reviews` table. This is the **only new stage**; everything
below already exists and consumes the reviews it produces.

### Stage 1 — Sentiment ([`sentiment.py`](app/backend/app/ml/sentiment.py))
Scores every review with `sentiment IS NULL` via the HuggingFace Inference API
(`cardiffnlp/twitter-xlm-roberta-base-sentiment`), falling back to VADER if the
API/token is unavailable. Produces `(label, compound ∈ [-1,1])`.

### Stage 2 — Store AI score ([`experience_score()`](app/backend/app/ml/sentiment.py#L113))
Per store: `experience_score = 0.7·avg(rating) + 0.3·sentiment_as_stars`, plus
`review_count`. This is the "AI score" shown in the UI.

### Stage 3 — Zones ([`zones.py`](app/backend/app/ml/zones.py))
Geo-clusters stores into named zones (KMeans), rewrites the `zones` table, and
reassigns `store.zone_id`. Runs before the recommender because `zone_id` is a
content feature.

### Stage 4 — Recommender ([`recommender.py`](app/backend/app/ml/recommender.py))
Hybrid collaborative-filtering + content model. Writes precomputed
`store_similarity` and `user_recommendations` so serving stays stateless.

---

## Runtime (request-path) ML — the deliberate exceptions
Two things run live because they must be interactive:
1. **Single-review sentiment** — `POST /reviews` scores one review in a
   background task ([`tasks.py:score_review`](app/backend/app/ml/tasks.py)) and
   refreshes that store's score immediately.
2. **Chatbot** — retrieval over our DB + optional Groq phrasing
   ([`ml/chatbot.py`](app/backend/app/ml/chatbot.py), [`chat/`](app/backend/app/chat/)).
Everything else is served from precomputed tables.

---

## Scheduled jobs

| Job | Schedule | Trigger | What it does |
|-----|----------|---------|--------------|
| Metro refresh | Mon 03:00 UTC | [`metro-refresh.yml`](.github/workflows/metro-refresh.yml) | Refresh metro stations from OSM → PR |
| **Reviews + AI score** | **Mon 04:00 UTC (weekly)** | **`reviews-refresh.yml` (new)** | **Ingest reviews → sentiment → recompute scores** |
| Full ML pipeline | manual / on deploy | `python -m app.ml.pipeline` | Stages 1–4 end-to-end |

---

## Where things live
| Concern | Path |
|---------|------|
| Source data | [`data/`](data/) |
| DB models | [`app/backend/app/models.py`](app/backend/app/models.py) |
| Seeding | [`app/backend/app/seed.py`](app/backend/app/seed.py) |
| Batch ML orchestrator | [`app/backend/app/ml/pipeline.py`](app/backend/app/ml/pipeline.py) |
| Review ingestion (new) | `app/backend/app/ml/ingest_reviews.py` |
| Sentiment / score | [`app/backend/app/ml/sentiment.py`](app/backend/app/ml/sentiment.py) |
| Zones / recommender | [`zones.py`](app/backend/app/ml/zones.py) · [`recommender.py`](app/backend/app/ml/recommender.py) |
| Serving API | [`app/backend/app/routers/`](app/backend/app/routers/) |
| Frontend | [`app/frontend/src/`](app/frontend/src/) |
| Config / secrets | [`config.py`](app/backend/app/config.py) · `.env` · GitHub secrets |

---

## Data-flow summary (one line)
`CSV/OSM → seed → DB → [weekly: ingest reviews → sentiment → score → zones → recommender] → read-only API → React map/chat`

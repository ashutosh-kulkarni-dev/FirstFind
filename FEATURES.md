# ThriftFind — Feature Deep Dives

> Covers the five core ML/data features in detail: sentiment analysis, recommendations, geospatial clustering, chatbot, and database design.

---

## Table of Contents

1. [Multilingual Sentiment Analysis](#1-multilingual-sentiment-analysis)
2. [Recommendation System](#2-recommendation-system)
3. [Geospatial Clustering](#3-geospatial-clustering)
4. [Chatbot](#4-chatbot)
5. [Database Design](#5-database-design)
6. [Feature Interconnections](#6-feature-interconnections)

---

## 1. Multilingual Sentiment Analysis

### Overview

Every review posted to ThriftFind is automatically scored for sentiment using a multilingual transformer model. The system handles English, Hinglish, and mixed-language reviews out of the box. The score feeds directly into each store's `experience_score`.

### Files

| File | Role |
|------|------|
| [app/backend/app/ml/sentiment.py](app/backend/app/ml/sentiment.py) | Core analyzer — HF API call, VADER fallback, score blending |
| [app/backend/app/ml/tasks.py](app/backend/app/ml/tasks.py) | Background task `score_review()` |
| [app/backend/app/ml/pipeline.py](app/backend/app/ml/pipeline.py) | Batch pipeline `score_pending_sentiment()` |
| [app/backend/app/routers/stores.py](app/backend/app/routers/stores.py) | `POST /stores/{store_id}/reviews` — triggers task |

### Models Used

- **Primary:** `cardiffnlp/twitter-xlm-roberta-base-sentiment` via HuggingFace Inference API
  - XLM-RoBERTa trained on 198M tweets in 100 languages
  - Handles Hinglish vocabulary: "bakwaas", "mast", "paisa vasool", "sasta"
- **Fallback:** VADER (`vaderSentiment`) — runs locally, no API key needed

### Pipeline — Four Stages

**Stage 1 — Real-time (on review post)**

```
POST /stores/{id}/reviews
  → Review saved: sentiment=NULL, sentiment_score=NULL
  → FastAPI BackgroundTask: score_review(review_id) fired
```

**Stage 2 — Background task**

```
score_review(review_id)                          # tasks.py:55
  → sentiment_ml.analyze(review_text)            # sentiment.py
  → httpx POST to HuggingFace Inference API
      URL: https://api-inference.huggingface.co/models/cardiffnlp/twitter-xlm-roberta-base-sentiment
      Auth: Bearer HUGGINGFACE_TOKEN
  → Parse response shape (handles both [{}] and [[{}]] variants)
  → Return (label, compound_score)               # label ∈ {positive, neutral, negative}
                                                 # score ∈ [-1.0, 1.0]
  → Update Review.sentiment, Review.sentiment_score
  → Recompute Store.experience_score
```

**Stage 3 — Batch (nightly pipeline)**

```
pipeline.score_pending_sentiment()              # pipeline.py:32
  → SELECT reviews WHERE sentiment IS NULL
  → Call sentiment.analyze() per row
  → Bulk UPDATE — flushes all at once
```

**Stage 4 — Store score aggregation**

The `experience_score` for each store blends star ratings and ML sentiment:

```
experience_score = 0.7 × avg_star_rating + 0.3 × sentiment_as_stars

where:
  sentiment_as_stars = (avg_sentiment_score + 1) / 2 × 4 + 1
  # maps [-1, 1] → [1, 5] scale
```

Weights: star rating 70%, sentiment 30%.

### Fallback Chain

```
HUGGINGFACE_TOKEN set?
  ├── YES → HF Inference API call
  │         ├── 200 OK → parse label + score
  │         └── Error/timeout → VADER fallback
  └── NO  → VADER SentimentIntensityAnalyzer (local)
              → compound score normalized to [-1, 1]
```

### Output Contract

```python
(label: str, compound_score: float)
# label  ∈ {"positive", "neutral", "negative"}
# score  ∈ [-1.0, 1.0]
```

---

## 2. Recommendation System

### Overview

A hybrid collaborative filtering + content-based recommender. It pre-computes both store-to-store similarity and per-user recommendations, persists them to the database, and serves them statelessly from any worker.

### Files

| File | Role |
|------|------|
| [app/backend/app/ml/recommender.py](app/backend/app/ml/recommender.py) | `Recommender` class — build, fit, persist, serve |
| [app/backend/app/ml/tasks.py](app/backend/app/ml/tasks.py) | `build_recommender()`, `refit_recommender()` |
| [app/backend/app/routers/stores.py](app/backend/app/routers/stores.py) | `GET /stores/{id}` returns `similar` list |
| [app/backend/app/routers/misc.py](app/backend/app/routers/misc.py) | `GET /api/recommendations` |
| [app/backend/app/models.py](app/backend/app/models.py) | `StoreSimilarity`, `UserRecommendation` tables |

### Algorithm — Hybrid CF + Content

#### Phase 1 — Collaborative Filtering

Build an interaction matrix **M** (users × stores) from logged events:

| Interaction | Weight |
|-------------|--------|
| view        | 1.0    |
| save        | 2.0    |
| like        | 3.0    |

Compute item-item cosine similarity:

```
CF_sim = cosine(M^T)
       = (M^T · M) / (||M^T|| · ||M||)
diagonal zeroed (a store is not similar to itself)
```

#### Phase 2 — Content Similarity

Build a feature matrix **X** (stores × features):

| Feature group | Encoding |
|---------------|----------|
| Categories    | Multi-hot (split by comma) |
| Price band    | 3 buckets: <₹250 / ₹250–600 / >₹600 |
| Zone          | One-hot (zone label) |
| Quality       | `experience_score / 5.0` (scalar) |

```
content_sim = cosine(X^T)
```

#### Phase 3 — Blending

```
similarity = α × CF_sim + (1 − α) × content_sim

ALPHA = 0.6   # CF dominates when interactions exist
              # content_sim bridges cold-start (new stores, new users)
```

### Serving Architecture

After fitting, results are written to two tables:

- `StoreSimilarity` — top-8 similar stores per store (with rank + score)
- `UserRecommendation` — top-12 stores per user (with rank + score)

API workers read from these tables. No in-memory model needed at serve time — survives restarts, identical across workers.

### Refit Trigger

```
User interaction (view/save/like) received
  → BackgroundTask: refit_recommender()
  → Debounced: skipped if last refit < 15s ago
  → EXCEPT save interactions: force=True (no debounce)
  → Recommender.build(db) → fit → persist → commit
```

### Key Parameters

| Parameter | Value | Effect |
|-----------|-------|--------|
| `ALPHA` | 0.6 | CF weight in hybrid blend |
| `WEIGHTS["view"]` | 1.0 | Weakest interaction signal |
| `WEIGHTS["save"]` | 2.0 | Mid-strength signal |
| `WEIGHTS["like"]` | 3.0 | Strongest signal |
| Similar stores persisted | 8 | Per store |
| User recs persisted | 12 | Per user |
| Refit debounce | 15 s | Prevents thrashing |

### API Endpoints

```
GET /api/recommendations
  Response: { personalized: bool, stores: [...] }

GET /stores/{store_id}
  Response includes: { similar: [{ match_pct, name, area, ... }, ...] }
```

---

## 3. Geospatial Clustering

### Overview

Stores are grouped into geographic clusters (zones) using HDBSCAN, with KMeans as a fallback. Zones are named after the dominant neighborhood, have a computed radius, and are used throughout the app — by the chatbot for location lookup, by the recommender as a feature, and shown on the map.

### Files

| File | Role |
|------|------|
| [app/backend/app/ml/zones.py](app/backend/app/ml/zones.py) | Batch zone computation — HDBSCAN, KMeans, naming, radius |
| [app/backend/app/ml/clusters.py](app/backend/app/ml/clusters.py) | Live cluster queries — find, split |
| [app/backend/app/routers/clusters.py](app/backend/app/routers/clusters.py) | REST API for cluster endpoints |
| [app/backend/app/ml/pipeline.py](app/backend/app/ml/pipeline.py) | `recompute_zones()` — pipeline stage |

### Two Clustering Modes

#### Mode A — Precomputed Zones (startup / nightly batch)

All visible stores are clustered into `N_ZONES = 4` zones.

```
Load all visible stores (lat, lng, area, locality_raw, price, experience_score)
  → Standardize (lat, lng) with StandardScaler
  → Try HDBSCAN(min_cluster_size=4)
      → If < 2 clusters produced: retry with mcs=5, then mcs=6
      → If still < 2 clusters: fall back to KMeans(k=4)
  → Reattach noise points (label=-1) to nearest centroid
  → Name each cluster: dominant area string (tiebreak: locality_raw frequency)
  → Compute radius: 90th-percentile haversine distance from centroid to members
       capped at MAX_RADIUS_KM = 10.0 km
  → Write Zone rows, assign store.zone_id
```

#### Mode B — Live Cluster Query (per API request)

```
POST /api/clusters/find?lat=X&lng=Y&radius_km=R
  → Haversine filter all visible stores within R km
  → Compute real_radius (90th percentile of member distances)
  → Compute dominant area label
  → Return single cluster dict
```

#### Mode B.2 — Cluster Splitting (overcapacity)

When a cluster has more than `DEFAULT_MAX_SHOPS = 8` stores, the frontend can request a split:

```
POST /api/clusters/split?lat=X&lng=Y&radius_km=R&max_shops=8
  → Try HDBSCAN with tightening min_cluster_size:
      for mcs in range(2, max(3, n / k_target) + 1):
          if all sub-clusters ≤ max_shops: return immediately
  → Fallback: KMeans(k = ceil(n / max_shops))   # always succeeds
  → Noise points reattached — union of sub-zones == original stores (no drops)
```

### Zone Data Structure

```python
Zone {
  id:          int           # PK
  label:       str           # "Koramangala", "Indiranagar", ...
  center_lat:  float
  center_lng:  float
  radius_km:   float         # 90th-pct haversine distance from centroid
  store_count: int
  avg_score:   float         # avg experience_score of members
  avg_price:   float         # avg price_min of members
}
```

### Cluster API Response

```json
{
  "label": "Koramangala",
  "center_lat": 12.9516,
  "center_lng": 77.6444,
  "radius_km": 1.2,
  "store_count": 7,
  "stores": [ { "id": "blr-0012", "name": "...", ... } ],
  "over_cap": false,
  "avg_score": 3.8,
  "avg_price": 450.0,
  "honest_empty": false
}
```

### Key Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `N_ZONES` | 4 | Target cluster count |
| `MAX_RADIUS_KM` | 10.0 km | Hard radius cap |
| `DEFAULT_MAX_SHOPS` | 8 | Threshold before split offered |
| `DEFAULT_MIN_SHOPS` | 3 | Minimum meaningful cluster |
| `WALKABLE_KM` | 1.2 km | UI threshold for "walkable zone" label |
| HDBSCAN mcs range | 4 → 6 | Progressive tightening before KMeans fallback |

---

## 4. Chatbot

### Overview

A 5-stage retrieval pipeline with optional LLM phrasing. The bot resolves location names from user messages, finds relevant stores using hard filters and soft ranking, assembles a rich context payload, and passes it to Groq for natural-language phrasing. Every response is grounded in real store data — the LLM cannot invent facts.

### Files

| File | Role |
|------|------|
| [app/backend/app/chat/engine.py](app/backend/app/chat/engine.py) | Main orchestrator `respond()` |
| [app/backend/app/chat/retrieval.py](app/backend/app/chat/retrieval.py) | `understand()`, `retrieve()`, `rank_stores()` |
| [app/backend/app/chat/geo.py](app/backend/app/chat/geo.py) | `locate()` — geospatial resolution |
| [app/backend/app/chat/contracts.py](app/backend/app/chat/contracts.py) | `Entities`, `GeoResult`, `Trip`, `ChatResult` dataclasses |
| [app/backend/app/ml/llm.py](app/backend/app/ml/llm.py) | `phrase_reply()` — Groq API call |
| [app/backend/app/routers/misc.py](app/backend/app/routers/misc.py) | `POST /api/chat` |

### Five Feature Pillars

| Pillar | Flag | What it enables |
|--------|------|-----------------|
| CHAT_GEO | `CHAT_GEO=true` | Geospatial engine — resolve location names to coords |
| CHAT_STATE | `CHAT_STATE=true` | Session memory across conversation turns |
| CHAT_TRIPS | `CHAT_TRIPS=true` | Shopping trip planning + refinement |
| CHAT_MAP | `CHAT_MAP=true` | Inline map spec + deep-link action in response |
| CHAT_ADVICE | `CHAT_ADVICE=true` | Curated shopping tips intent |

### Full Request Pipeline

```
POST /api/chat { message, session_id, origin }
  │
  ├─ GREETING_RE → short-circuit (skip ML for hellos)
  │
  ├─ [CHAT_STATE] Load session (previous trip, preferences)
  │
  ├─ Stage 1: understand(msg, db)
  │    → Normalize: lowercase, collapse repeats, strip punctuation
  │    → Intent detection: regex patterns + fuzzy keyword fallback
  │    → Entity extraction:
  │        Area:     exact substring → fuzzy word-window match against DB areas
  │        Locality: token-overlap against locality_raw if Tier 1 fails
  │        Category: synonym dictionary lookup
  │        Price:    regex extract rupee amount
  │    → Returns Entities(intent, area, category, price_ceiling, ...)
  │
  ├─ [CHAT_GEO] geo.locate(db, entities) → GeoResult | None
  │    → Precedence (highest → lowest):
  │        1. "near me" + browser origin (lat, lng passed from client)
  │        2. Area string → centroid from cached (area → coords) map
  │        3. Gazetteer hit (B2 place index)
  │        4. Locality token-match on locality_raw
  │    → Calls find_cluster(db, lat, lng, radius_km)
  │    → Attaches nearest metro station (haversine from metro_stations_blr.json)
  │    → Returns GeoResult { store_ids, center, radius_km, nearest_metro }
  │
  ├─ [CHAT_TRIPS] Check trip-refinement intent before full retrieval
  │    → If prior trip in session + intent ∈ {reorder, drop, cheaper, open_only}:
  │        Filter/sort trip.store_ids in-place → skip Stage 2 retrieval
  │
  ├─ Stage 2–3: retrieve(db, entities, geo_store_ids) + assemble context
  │    HARD filters (strict — excluded stores never appear):
  │      • Store has lat/lng (visible)
  │      • Area matches entities.area (Tier 1: exact; Tier 2: locality token-overlap)
  │      • If geo_store_ids provided: restrict to that set
  │    SOFT scores (never exclude — only rank):
  │      • W_QUALITY    = 2.0 × (experience_score / 5.0)
  │      • W_CATEGORY   = 1.5  (if store.categories matches entities.category)
  │      • W_PRICE      = 1.0 × (1 − price_min / ceiling)
  │      • W_POPULARITY = 0.3 × (min(review_count, 20) / 20)
  │      • W_OPEN       = 1.5  (if open right now — soft signal, never hard filter)
  │      • W_PREF_LIKED = 1.2  (user previously liked this store — CHAT_STATE)
  │      • W_PREF_DISLIKE = −2.0 (user disliked — CHAT_STATE)
  │    Context assembled per store:
  │      name, area, categories, price_min/max, open/close times, is_open_now,
  │      phone, instagram, notes, experience_score, review_count, zone label,
  │      sentiment_summary { positive, neutral, negative, total },
  │      review_snippets (top 2, if review_insight intent)
  │
  ├─ Stage 4: dispatch(ctx) → Draft { reply, stores, suggestions }
  │    Rule-based handler per intent — grounded in retrieved stores only
  │
  ├─ [CHAT_TRIPS] build_trip(stores, geo_result) → Trip { store_ids, center, radius_km }
  │
  ├─ [CHAT_STATE] save_session(session_id, trip, entities)
  │
  ├─ Stage 5: phrase_reply(msg, draft, context, intent)
  │    → POST to Groq API (if GROQ_API_KEY set, timeout 8s)
  │    → System prompt constrains: only use facts from context, never invent
  │    → On any failure → fall back to rule-based draft text
  │
  └─ [CHAT_MAP] build_map(geo_result, trip, stores) → map_spec, action
       → GeoJSON FeatureCollection + fit_bounds action for frontend map

Return: ChatResult { reply, intent, stores, suggestions, map, action, trip }
```

### Supported Intents

| Intent | Trigger example |
|--------|----------------|
| `find_by_area` | "stores in Indiranagar" |
| `find_by_category` | "vintage shops" |
| `find_by_price` | "under ₹300" |
| `open_now` | "what's open right now?" |
| `zone_exploration` | "what's in this area?" |
| `store_recommendation` | "suggest something good" |
| `review_insight` | "what do people say about..." |
| `store_comparison` | "compare these two" |
| `best_time_to_visit` | "when should I go?" |
| `shopping_advice` | "tips for thrifting" |
| `general_assistance` | anything else |

### Geospatial Name Resolution in Detail

The chatbot resolves plain-text location mentions in two tiers:

**Tier 1 — Canonical areas (from DB)**
Loaded at process startup. Exact substring match against `Store.area` values.
Example: "Koramangala" → exact match → area centroid

**Tier 2 — Locality phrases (fuzzy)**
If Tier 1 fails, token-overlap match against `Store.locality_raw` strings.
Example: "Tavrekere Road" → locality_raw fuzzy match → centroid of matching stores

**Tier 3 — Gazetteer (B2 place index)**
Named place lookup → (lat, lng) only, no area affinity.

**Tier 4 — "near me"**
Client sends `origin: { lat, lng }` → highest priority if present and message contains "near me".

After resolving a (lat, lng) center, `find_cluster()` is called with `LOCATION_RADIUS_KM = 2.0 km` to get the actual store set. The nearest metro station (from `data/metro_stations_blr.json`) is attached to the response.

### Chatbot API

```
POST /api/chat
{
  "message":    "Show me vintage stores near Koramangala",
  "session_id": "uuid-123",
  "origin":     { "lat": 12.9516, "lng": 77.6444 }   // optional
}

Response:
{
  "reply":       "Found 5 vintage stores in Koramangala...",
  "intent":      "find_by_category",
  "stores":      [{ "id": "blr-0012", "name": "...", ... }],
  "suggestions": ["Show cheaper options", "Which are open now?"],
  "map":         { "type": "FeatureCollection", "features": [...] },
  "action":      { "type": "fit_bounds", "bounds": [...] },
  "trip":        { "store_ids": ["blr-0012", ...], "center": [12.95, 77.64], ... }
}
```

---

## 5. Database Design

### Core Tables

#### `users`
User accounts, supporting both email/password and Google OAuth.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `email` | unique | |
| `name` | str | |
| `password_hash` | nullable | null for OAuth users |
| `auth_provider` | str | `"local"`, `"google"`, `"system"` |
| `google_sub` | unique, nullable | OAuth subject claim |
| `avatar_url` | nullable | |
| `created_at` | datetime | |

#### `stores`
The primary thrift store catalog. ML-computed columns are denormalized here for fast serving.

| Column | Type | Notes |
|--------|------|-------|
| `id` | str PK | Format: `"blr-0001"` |
| `name` | str | |
| `area` | str | Canonical neighborhood |
| `city` | str | |
| `lat`, `lng` | float, nullable | Null = hidden from users |
| `open_time`, `close_time` | str | HH:MM format |
| `closed_days` | str | CSV, e.g. `"Monday,Tuesday"` |
| `categories` | str | CSV, e.g. `"vintage,books"` |
| `price_min`, `price_max` | float, nullable | |
| `locality_raw` | str | Raw sub-locality string |
| `geocode_precision` | str | `"rooftop"`, `"neighborhood"`, etc. |
| `google_place_id` | nullable | For Places API ingestion |
| `phone`, `instagram`, `notes` | nullable | |
| **`experience_score`** | float | **ML-computed**: 0.7×rating + 0.3×sentiment |
| **`review_count`** | int | **ML-computed**: total review count |
| **`zone_id`** | FK → zones | **ML-assigned**: from recompute_zones() |

#### `reviews`
User-submitted and externally ingested reviews.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `store_id` | FK → stores | |
| `user_id` | FK → users | |
| `rating` | int 1–5 | |
| `text` | str | |
| `source` | str | `"app"` or `"google"` |
| `external_id` | nullable | Stable hash for dedup |
| `created_at` | datetime | |
| **`sentiment`** | str, nullable | **ML**: `positive` / `neutral` / `negative` |
| **`sentiment_score`** | float, nullable | **ML**: [-1.0, 1.0] |

Unique constraint: `(store_id, source, external_id)` — prevents re-ingesting the same external review.

#### `interactions`
User behavior signals for the recommender.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `user_id` | FK → users | indexed |
| `store_id` | str | |
| `kind` | str | `"view"`, `"save"`, `"like"` |
| `created_at` | datetime | |

#### `zones`
Precomputed geospatial clusters.

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `label` | str | Dominant area name |
| `center_lat`, `center_lng` | float | Cluster centroid |
| `radius_km` | float | 90th-pct haversine distance |
| `store_count` | int | Members |
| `avg_score` | float | Avg experience_score |
| `avg_price` | float | Avg price_min |
| `description` | nullable | Optional human note |

#### `store_similarity`
Precomputed nearest-neighbor results for the recommender (stateless serving).

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `store_id` | FK → stores | indexed |
| `similar_id` | FK → stores | |
| `rank` | int | 1 = most similar |
| `score` | float | Hybrid similarity score |

#### `user_recommendations`
Precomputed per-user store recommendations (stateless serving).

| Column | Type | Notes |
|--------|------|-------|
| `id` | PK | |
| `user_id` | FK → users | indexed |
| `store_id` | FK → stores | |
| `rank` | int | |
| `score` | float | |

#### `conversations` + `chat_messages`
Chat history storage.

| Table | Key Columns |
|-------|-------------|
| `conversations` | `id`, `user_id (indexed)`, `session_id`, `title`, `created_at`, `updated_at` |
| `chat_messages` | `id`, `conversation_id (FK)`, `role ("user"/"assistant")`, `text`, `meta (JSON)`, `created_at` |

#### `saved_lists` + `saved_list_items`
User-curated store lists (e.g. a trip the chatbot built).

| Table | Key Columns |
|-------|-------------|
| `saved_lists` | `id`, `user_id (FK)`, `name`, `center_lat/lng`, `radius_km`, `source_label`, `created_at` |
| `saved_list_items` | `id`, `list_id (FK)`, `store_id (FK)`, `position` |

### Design Patterns

**Intentional Denormalization**

Several columns are pre-computed and stored on the parent table for fast reads:

| Denormalized column | Computed from | Updated by |
|--------------------|---------------|-----------|
| `Store.experience_score` | All reviews for that store | `recompute_store_scores()` in pipeline |
| `Store.review_count` | COUNT of reviews | Same |
| `Store.zone_id` | Clustering run | `recompute_zones()` |
| `Zone.store_count` | COUNT of member stores | `recompute_zones()` |
| `Zone.avg_score` | AVG experience_score of members | `recompute_zones()` |
| `StoreSimilarity` rows | Full recommender fit | `Recommender.fit()` |
| `UserRecommendation` rows | Full recommender fit | `Recommender.fit()` |

This trades some write complexity for completely stateless API serving — any worker can answer any request from DB reads alone.

**Store Visibility Policy**

Stores without coordinates (`lat IS NULL OR lng IS NULL`) are kept in the database for future manual pinning but are excluded from all user-facing queries. A shared filter constant is applied everywhere:

```python
STORE_HAS_COORDS = (Store.lat.isnot(None), Store.lng.isnot(None))
```

**External Review Deduplication**

External (Google) reviews use a composite unique constraint:

```sql
UNIQUE (store_id, source, external_id)
```

`external_id` is a SHA-1 hash of the review content. This makes the ingestion pipeline safe to re-run at any time — duplicate inserts are silently ignored.

All ingested reviews are attributed to a system bot user (`reviews-bot@thriftfind.local`, `auth_provider="system"`), keeping real user identities clean.

**Schema Evolution**

New columns are added via `ensure_schema()` which issues `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` at startup. This avoids Alembic migrations for additive changes.

### ML Pipeline Stages (in order)

| Stage | Function | What it writes |
|-------|----------|----------------|
| 1 | `score_pending_sentiment()` | `Review.sentiment`, `Review.sentiment_score` |
| 2 | `recompute_store_scores()` | `Store.experience_score`, `Store.review_count` |
| 3 | `recompute_zones()` | `Zone` rows (delete + reinsert), `Store.zone_id` |
| 4 | `Recommender.build()` | `StoreSimilarity`, `UserRecommendation` |

The full pipeline runs inside a single transaction — it rolls back entirely on any exception.

### Data Consistency Mechanisms

| Mechanism | How |
|-----------|-----|
| Atomic pipeline | `with db.begin()` wraps all 4 stages |
| Ingest idempotency | Unique constraint on `(store_id, source, external_id)` |
| Recommender debounce | 15 s minimum between refits (except saves: force=True) |
| Off-request ML | HF API calls via `BackgroundTask` — never on request path |
| Schema evolution | `ALTER TABLE IF NOT EXISTS` at startup |

### Supported Databases

- **Development:** MySQL (local default)
- **Production:** PostgreSQL via Supabase (`DATABASE_URL` env var)
- All queries written with SQLAlchemy ORM — no DB-specific code in application logic.

### Auth & Sessions

| Aspect | Detail |
|--------|--------|
| Token format | JWT, HS256 |
| Token expiry | 7 × 24 hours |
| Guest sessions | Ephemeral — can be claimed at registration |
| Chat sessions | UUID-based, optionally linked to `user.id` |

---

## 6. Feature Interconnections

The five features are tightly coupled at the data level. Here is how they feed each other:

```
[Review posted]
      │
      ▼
Sentiment analysis (HF/VADER)
  → sentiment + sentiment_score on Review
      │
      ▼
Store score recompute
  → experience_score on Store (rating 70% + sentiment 30%)
      │
      ├─────────────────────────────────────────────────┐
      ▼                                                 ▼
Recommender fit                                 Geospatial clustering
  uses experience_score as a content feature     uses experience_score for Zone.avg_score
  uses zone_id for content one-hot               writes zone_id back onto Store
      │                                                 │
      ▼                                                 ▼
StoreSimilarity + UserRecommendation            Zone rows (label, center, radius)
  served by GET /api/recommendations               used by chatbot geo resolution
  served by GET /stores/{id} similar list          used by recommender zone feature
                                                       │
                                                       ▼
                                               Chatbot Stage 1 (understand)
                                                 resolves "Koramangala" → Zone centroid
                                               Chatbot Pillar 1 (geo.locate)
                                                 calls find_cluster → live store set
                                               Chatbot Stage 2–3 (retrieve + rank)
                                                 experience_score drives W_QUALITY rank
                                                 zone label in context payload
                                               Chatbot Stage 5 (phrase_reply)
                                                 Groq LLM phrases from context
                                                 falls back to rule-based draft
```

### Summary Table

| Feature | Algorithm | Model / Library | Key DB tables | API |
|---------|-----------|----------------|---------------|-----|
| Sentiment | HF Inference API + VADER fallback | `cardiffnlp/twitter-xlm-roberta-base-sentiment`, `vaderSentiment` | `reviews` | `POST /stores/{id}/reviews` |
| Recommender | Hybrid CF + content cosine, α=0.6 | scikit-learn | `StoreSimilarity`, `UserRecommendation` | `GET /api/recommendations`, `GET /stores/{id}` |
| Geospatial | HDBSCAN → KMeans fallback, 90th-pct radius | scikit-learn, numpy | `zones` | `GET /api/clusters`, `/clusters/find`, `/clusters/split` |
| Chatbot | 5-stage: regex NLU → geo → retrieve → dispatch → Groq | Groq API (optional) | `conversations`, `chat_messages` | `POST /api/chat` |
| Database | Normalized + selective denormalization | SQLAlchemy, MySQL/PostgreSQL | All above + `users`, `interactions`, `saved_lists` | — |

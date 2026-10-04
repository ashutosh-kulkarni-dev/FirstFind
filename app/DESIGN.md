# ThriftFind MVP — System & UI Design

MVP implementation of the platform specified in the SRS: conversational thrift-store discovery for Bengaluru, powered by four lightweight ML modules over the real 48-store dataset in `data/stores.json`.

## Architecture

```
┌────────────────────────── Frontend (React + Vite, :5173) ──────────────────────────┐
│  Landing (Three.js hero) · Explore (Leaflet map) · Chat · Store Detail · Zones      │
│  Floating chat widget on every page · JWT kept in sessionStorage                    │
└───────────────────────────────┬─────────────────────────────────────────────────────┘
                                │  /api/* (Vite dev proxy → :8000)
┌───────────────────────────────▼───────────── Backend (FastAPI, :8000) ──────────────┐
│  Middleware: CORS · request timing/logging · sliding-window rate limiter            │
│  Routers: /auth · /stores · /zones · /recommendations · /chat                       │
│  ┌── ML layer ────────────────────────────────────────────────────────────────┐    │
│  │ chatbot.py     rule-based intent engine (10 intents) — routes to modules    │    │
│  │ sentiment.py   VADER → review labels + blended experience score             │    │
│  │ anomaly.py     Isolation Forest → flags suspicious reviews                  │    │
│  │ zones.py       K-Means (k=4) → Budget/Premium/Mixed/Hidden Gem zones        │    │
│  │ recommender.py item-item cosine CF over user interactions                   │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│  SQLite (SQLAlchemy ORM) — seeded from data/stores.json at first startup            │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Request flow example — "vintage under ₹500 in Koramangala"
1. Frontend POSTs `/api/chat` (optional JWT).
2. Rate-limit + timing middleware pass the request through.
3. `chatbot.detect_intent` → `find_by_price`; entity extraction pulls area=Koramangala, category=vintage, price=500.
4. Store query filters + sorts by experience score (already anomaly-filtered + sentiment-blended).
5. Response: natural-language reply + store cards + intent tag, rendered in the chat UI.

## Data model (SQLite)

| Table | Key fields | Notes |
|---|---|---|
| `stores` | id (blr-XXXX), name, area, lat/lng, timings, categories, price band, `experience_score`, `zone_id` | 48 real stores; categories/prices are synthetic enrichment (`enrichment_synthetic=1`) |
| `users` | email, name, pbkdf2 password hash | 14 synthetic demo users + real registrations |
| `reviews` | rating, text, `sentiment`, `sentiment_score`, `is_flagged` | ~450 synthetic; new reviews scored live |
| `interactions` | user↔store, kind (view/save/like) | feeds collaborative filtering |
| `zones` | label, center, store_count, avg_score, avg_price | K-Means output |

**Honest labelling:** real fields (names, areas, coordinates, timings, phones) come from your field data and are never fabricated. Reviews, interactions, categories and prices are deterministic synthetic demo data, flagged `is_synthetic` in the DB and disclosed in the UI footer. Swap them out as real users arrive — no code changes needed.

## ML design decisions (vs SRS spec)

| SRS spec | MVP implementation | Why |
|---|---|---|
| CardiffNLP RoBERTa sentiment | VADER lexicon model | Zero download, same interface (`analyze(text) → label, score`); swap in RoBERTa later by editing one function |
| SVD (Surprise lib) CF | Item-item cosine similarity | Surprise needs compilation on Windows; cosine CF is defensible, transparent, and handles the same interaction matrix |
| Isolation Forest | Isolation Forest (as specced) | Features: text length, rating, account age, reviewer volume. Seed data includes a deliberate fake-review burst so the demo shows real flags |
| K-Means zones | K-Means (as specced) | Geo-dominant feature weighting; labels derived from price/score/review-count distribution |

The experience score = 0.7 × mean star rating + 0.3 × sentiment (rescaled to 1–5), computed **only over non-flagged reviews** — so the anomaly module visibly protects the score.

## API surface

```
POST /api/auth/register      → {token, name, email}
POST /api/auth/login         → {token, name, email}
GET  /api/stores?area&category&price_max&open_now&q
GET  /api/stores/areas
GET  /api/stores/nearby?lat&lng&radius_km
GET  /api/stores/{id}        → detail + reviews + sentiment summary + similar stores
POST /api/stores/{id}/reviews   (auth) → live sentiment + score recompute
POST /api/stores/{id}/save      (auth) → interaction for CF
GET  /api/zones
GET  /api/recommendations    → personalized if authed w/ history, else top-rated fallback
POST /api/chat               → {reply, intent, stores[], suggestions[]}
GET  /api/health
```

## UI design

**Direction:** dark, editorial, "acid-thrift" — deep charcoal-green base (`#0c0f0d`), acid-lime accent (`#c8f048`), terracotta secondary (`#f4a988`). Space Grotesk display type, Inter body, glass cards, film-grain overlay, pill buttons with lime glow.

- **Landing** — Three.js hero: drifting two-tone particle field + wireframe torus-knot ("thread ball") with mouse parallax. ~1,200 points, no post-processing, capped pixel ratio → 60fps on integrated GPUs. Live stats pulled from the API.
- **Explore** — split view: filter sidebar (area/category/budget/open-now/search) + CARTO dark-matter Leaflet map. Pins colour-coded by score per SRS (green ≥4.0, amber 3.0–3.9, red <3.0, grey unrated).
- **Assistant** — full-page chat: intent tag under each reply, store cards inside messages, suggestion chips, typing indicator. Same engine reused in a floating dock widget on every other page (SRS FR-1.1).
- **Store detail** — AI score ring, sentiment distribution bar, reviews with sentiment badges, flagged reviews dimmed behind a "show" toggle with ⚠ badge, review composer (live sentiment on submit), "shoppers also liked" from CF.
- **Zones** — dashed zone circles on the map + per-zone cards (store count, avg score, avg price, top stores).

## Security / middleware notes
- JWT (HS256, 7-day expiry) via `Authorization: Bearer`; guests get graceful fallbacks everywhere, per SRS.
- Passwords: PBKDF2-HMAC-SHA256, 120k iterations, per-user salt.
- Sliding-window rate limiter (120 req/min/IP) + request timing logs (`X-Response-Time`).
- MVP gaps (deliberate): no refresh tokens, no email verification, SQLite not Postgres, rate limiter is in-memory. All fine at this scale; called out so you can defend them in a viva.

## What I'd build next
1. Replace synthetic reviews with a real crowdsourcing flow + moderation queue.
2. Store-owner claim/verify flow (your SRS mentions owner visibility).
3. Postgres + Alembic migrations once data is real.
4. Session-level conversation context in the chatbot (follow-up queries).

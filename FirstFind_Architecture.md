# FirstFind — Architecture Plan

Two architectures: the **full app** (what you build over the capstone) and the **MVP demo** (what you show first, running on dummy data). The MVP is a strict subset of the full app — nothing built for the demo gets thrown away.

---

## Part 1: Full App Architecture

### Layer overview

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND — React + Leaflet (Vercel, free)              │
│  Mobile-first. Map view, store pages, chat UI, auth UI  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS (student-pack domain)
┌──────────────────────▼──────────────────────────────────┐
│  BACKEND — DigitalOcean droplet ($6/mo from $200 credit)│
│  Nginx → Gunicorn (sync workers) + Uvicorn (async)      │
│                                                          │
│  Django + DRF                                            │
│  ├─ Store/search/review/auth APIs (sync views)          │
│  ├─ Chatbot view (ASYNC view, httpx → Groq)             │
│  └─ Django Admin = moderation dashboard                 │
│                                                          │
│  PostgreSQL + PostGIS + pgvector (same droplet)          │
│  ├─ stores (geom, price_band, category, quality_score,  │
│  │          zone_id — precomputed columns)              │
│  ├─ reviews (text, sentiment_score, embedding)          │
│  └─ users, saved_stores, interactions                   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  ML BATCH LAYER — cron on the droplet (nightly/weekly)  │
│  ├─ Sentiment scoring: HF Inference API on new reviews  │
│  │   → writes sentiment_score, recomputes quality_score │
│  ├─ Recommendations: content-based (LightFM later)      │
│  │   → writes user→store score table                    │
│  ├─ Zones: HDBSCAN on coords+price+quality (weekly)     │
│  │   → writes zone_id per store                         │
│  └─ Review embeddings: HF API → pgvector (for RAG)      │
└─────────────────────────────────────────────────────────┘

External APIs: Groq (chatbot LLM, free tier) · HF Inference API
(classification/embeddings only) · Google Places API (data collection only)
```

### Key design rules

1. **The web app never runs ML in-process.** Every score, recommendation, and zone is a precomputed database column. Serving a page = a SQL read. This is what makes a $6 droplet enough.
2. **Only the chatbot view is async.** All other views are sync Django — they're fast Postgres queries with nothing external to wait on. Async everywhere adds ORM complexity (`sync_to_async`) for zero gain.
3. **Sentiment scoring is deferred, not synchronous.** Reviews are saved instantly; the nightly cron scores pending ones via HF API. Users never wait on a model.
4. **HF API for one-shot classification only; Groq for conversation.** HF free credits (~$0.10/mo) die fast on chat but are fine for scoring/embedding single texts.

### Chatbot flow (the only real-time ML path)

```
User message
  → Django async view
  → Groq call #1: extract intent as JSON
      {area, price_band, category, question_type}
  → Branch:
      structured query  → PostGIS/SQL filter (exact, free)
      opinion question  → pgvector similarity over review embeddings (RAG)
  → Groq call #2: phrase DB results conversationally
  → Response to user
```

Two short LLM calls per turn. Retrieval always happens in your own DB.

### Component → tool summary

| Component | Tool | Hosting |
|---|---|---|
| Frontend | React + Leaflet + OSM tiles | Vercel (free) |
| Backend | Django + DRF, async chatbot view | DO droplet ($200 credit) |
| Database | PostgreSQL + PostGIS + pgvector | Same droplet |
| Quality scoring | cardiffnlp twitter-roberta via HF Inference API | Nightly cron |
| Recommendations | Content-based → LightFM when interaction data exists | Nightly cron |
| Zone clustering | HDBSCAN (scikit-learn/hdbscan) | Weekly cron |
| Chatbot LLM | Groq free tier (Llama 3.3 70B) | API |
| Moderation | Django Admin | Built-in |
| Auth | Django auth + DRF JWT | Built-in |
| Domain | Namecheap .tech/.me (student pack) | Free 1 yr |
| Dropped for now | Fake review detection (Isolation Forest) | Re-add later if guide requires |

### Data flow for real data (post-MVP)

Field visits + Google Places API + crowd submissions → land as `pending` rows → approved via Django Admin → become visible → cron jobs score/cluster them.

---

## Part 2: MVP Demo Architecture

**Goal of the MVP:** prove every pipe works end-to-end — map search, store pages with scores, recommendations, zones, chatbot — using synthetic data. Not to prove the scores are *right* (they can't be, on fake data).

### What changes vs. the full app

| Aspect | Full app | MVP demo |
|---|---|---|
| Data | Field visits + Places API + crowd | **Seed script with dummy data** |
| Recommendations | Content-based / LightFM, nightly | Content-based, **run once manually** |
| Zones | HDBSCAN weekly cron | **Run once manually** |
| Sentiment | Nightly cron via HF API | **Run once manually** on seeded reviews |
| Cron jobs | Scheduled on droplet | None — one `python manage.py seed_and_score` command |
| Crowd submissions / moderation queue | Full workflow | Skip (Admin still exists for free) |
| Domain | Student-pack domain | Optional — droplet IP or default URL is fine |
| Auth | Full | Minimal: register/login + save-store, enough to demo personalization |

Everything else — stack, hosting, schema, chatbot flow — is **identical**. The MVP is the full app with cron replaced by one manual command and real data replaced by seeds.

### Dummy data plan

One management command, `seed_demo`:

1. **Stores (~150):** generated with Faker, but coordinates placed around *real* Bengaluru thrift areas — Commercial Street, Koramangala, Jayanagar 4th Block, Indiranagar, Majestic — with realistic scatter, plus a few isolated outliers. This makes HDBSCAN produce believable zones and outliers instead of noise.
2. **Reviews (~1,000–1,500):** template + variation generation with deliberate sentiment mix per store (some stores seeded positive, some mixed, some negative) so quality scores visibly differ across stores in the demo.
3. **Users + interactions (~30 users):** each seeded user saves/views stores in a pattern (e.g., "budget hunter", "vintage lover") so recommendations look coherent per persona.
4. Run the batch pipeline once: sentiment → quality scores → zones → recommendation table → embeddings.

**Honest caveat to state in your demo/report:** on synthetic data, the scores validate the *pipeline*, not the *models*. Don't present demo-day quality scores or zones as findings — evaluators will ask, and "these are pipeline-validation outputs on synthetic data; real evaluation follows data collection" is the right answer.

### MVP demo script (what you show, in order)

1. Open map → stores appear with filters (price, category, quality score) — *PostGIS + Leaflet working*
2. Click a store → detail page with quality score + reviews — *sentiment pipeline working*
3. "You might also like" on the store page — *recommendation table working*
4. Toggle zone view → colored clusters over Commercial St / Koramangala — *HDBSCAN working*
5. Ask the chatbot "cheap thrift stores near Koramangala" → conversational answer with real DB results — *Groq intent → SQL → Groq phrasing working*
6. Log in, save a store, show recommendations differ per user — *auth + personalization working*

### MVP build order

1. Django project + models + PostGIS setup on droplet; React + Leaflet skeleton on Vercel
2. `seed_demo` command (stores → reviews → users)
3. Store list/detail APIs + map with filters
4. Batch pipeline scripts (sentiment via HF, quality score, HDBSCAN, recommendations) — run manually
5. Chatbot view (async, Groq two-call flow) — structured queries first, RAG second
6. Auth + save-store + per-user recommendations
7. Polish demo script, warm everything up before presenting

Steps 1–3 give you a demoable map product even if 4–6 slip. Build in this order so a schedule overrun degrades the demo instead of killing it.

# ThriftFind — Bug & Defect Report

> **Update 2026-08-05 — resolved:** The fake-review detector (anomaly module) was **removed** entirely along with the planted fake reviews (C1). The recommender now refits on every interaction so real logged-in users get personalized picks; guests stay on the top-rated fallback (C2). All Major items fixed: zone-query routing (M1), four distinct zone archetypes now generated (M2), raw localities canonicalised so areas no longer fragment (M3), all 48 stores backfilled with coordinates → on the map and in a zone (M4), implausible `00:00` hours sanitised and opening hours evaluated in IST (M5). Verified end-to-end against a fresh seed. Details per item below.

**Date:** 2026-08-05
**Method:** Full source read (backend + frontend) + live black-box testing — fresh DB seed, backend booted on `:8000`, all 11 API endpoints exercised, all 10 chatbot intents driven, auth/review/recommendation flows run end-to-end, frontend production build, DB inspected directly.

**Headline:** The app **does not crash** — 45 requests, zero 500s, seed and build both succeed. Every defect below is a **silent correctness bug**: the app confidently returns *wrong* results. For a project whose entire pitch is "AI scores you can trust," the ML layer is the weakest part — two of the four "brains" are effectively producing garbage, and the app markets features it never actually delivers.

Severity legend: 🔴 Critical (feature is inverted/broken) · 🟠 Major (wrong results / dead feature) · 🟡 Minor (polish, edge cases).

---

## 🔴 CRITICAL

### C1. Anomaly detection is inverted — it flags real reviews and misses every planted fake
- **The single most important ML claim in the app is false.** `DESIGN.md` and the Landing page say the anomaly module "throws out the fake ones" and the seed "includes a deliberate fake-review burst so the demo shows real flags."
- **Measured reality (fresh seed, deterministic `SEED=42`):**
  - **0 of 12** deliberately-planted fake burst reviews are flagged.
  - **21 of 22** flagged reviews are *genuine Google Maps reviews*.
- Concrete example — store `blr-0001` **EcoDhaga**: two authentic positive Google reviews ("Really nice place, good pieces at affordable rates too", "loved this place!! it's a little bit hard to find…") are flagged as **suspicious** and **excluded from the experience score**, while the fake `"best store ever!!!!! 5 star"` burst sails through unflagged.
- **Root cause** — feature engineering in `seed.py` + `ml/anomaly.py`:
  - The "account age at review time" feature is meaningless. Real reviewer accounts get a **random** `created_at` (`_REF_DATE - randint(30,730)` in `_load_real_reviews`) that is unrelated to when their review was actually written. Many real reviews end up *predating* their own account (negative age → clamped to `0` by `max(0, …)` in `_seed_all`), so the burst accounts' genuinely-young age no longer stands out.
  - The burst is only 12 rows in a 272-row set at `contamination=0.08`; with noisy features the Isolation Forest isolates the naturally-long/short real reviews instead.
- **Impact:** the flagship "trustworthy AI score" is computed over a set that *excludes real reviews and includes fakes*. The anomaly demo shows the exact opposite of what it claims. **This corrupts every downstream number** (experience_score, sentiment summary, store ranking, zone avg_score, "shoppers also liked").
- Files: `backend/app/seed.py:150-166` (random account age), `backend/app/seed.py:301-312` (feature build), `backend/app/ml/anomaly.py`.

### C2. Personalized recommendations never work for real users
- The recommender is fit **exactly once**, at startup (`main.py::_fit_recommender`), from interactions that existed at seed time. It is **never refit**.
- `recommender.recommend_for_user` returns `[]` for any `user_id` not in the startup matrix (`recommender.py:37`). Every newly-registered user falls into that bucket **forever** (until a manual backend restart).
- **Verified live:** registered a new account, saved + viewed 3 stores, then called `/api/recommendations` → `personalized: false`; chatbot "recommend for me" → *"You haven't interacted with enough stores yet."* Interactions **are** written to the DB — they just never reach the model.
- **Impact:** the copy "log in and interact with a few stores to unlock personalized picks" (chatbot + Auth page) is a promise the app **cannot keep**. Only the 12 synthetic seed users ever get personalized results. The entire collaborative-filtering feature is dead for actual end-users.
- Files: `backend/app/main.py:15-24`, `backend/app/ml/recommender.py:36-45`, `backend/app/routers/misc.py:39-53`.

---

## 🟠 MAJOR

### M1. README/DESIGN flagship query "where are the budget thrift zones?" is misrouted
- Intent detection sends it to **`find_by_price`**, not `zone_exploration`, so the user asking about *zones* gets a list of *cheap stores* ("Stores with prices starting under ₹500:").
- **Root cause** (`ml/chatbot.py:33-43`): `zone_exploration`'s regex matches `\bzone\b` but the word is "zone**s**" — `\bzone\b` fails on the plural. The message then falls through to `find_by_price`, whose pattern greedily matches `\bbudget\b`.
- Verified live: the exact README example returns intent `find_by_price`. Also affects "budget thrift zones", "premium zones", etc.
- **Fix:** match `zones?` and/or reorder so zone detection wins over the `budget` price keyword.

### M2. "Hidden Gem Zone" is advertised everywhere but never generated
- Landing, Zones page, and `zones.py::ZONE_DESCRIPTIONS` promise four distinct zones: **Budget / Premium / Mixed / Hidden Gem**.
- Actual K-Means output (deterministic): **Mixed Zone, Premium Zone, Budget Zone, Mixed Zone 2** — two "Mixed", **no Hidden Gem at all**.
- The labelling thresholds in `zones.py:59-66` (`z_reviews.mean() < city_reviews_med*0.75 and avg_score >= 3.6`) never fire for this dataset, and two clusters both land in "Mixed", producing the confusing `"Mixed Zone 2"` label shown to users.
- **Impact:** a headline feature (4 named zone archetypes) is not delivered; the UI shows a meaningless "Mixed Zone 2".
- File: `backend/app/ml/zones.py:48-85`.

### M3. Area filtering is fragmented by dirty `locality_raw` data
- `stores.json` `locality_raw` is used verbatim as the canonical area (`seed.py:203`), and all filtering is **exact string match** (`Store.area == area`).
- The `/api/stores/areas` list is a mess of ~40 inconsistent values, with the same place split across many:
  - `Electronic City` (1 store) **vs** `Electronic City,Bengaluru` (1 store)
  - `JP Nagar` (2) **vs** `3rd Phase,JP Nagar` (1) **vs** `J.P Nagar 5th Phase` (1) **vs** `RBI Layout,JP Nagar` (1)
  - Non-areas leak in as "areas": `211, Rhs Plaza, 253, 14th Main Rd, Sector 7, Hsr Layout, Bengaluru`, `Opp Old Zara Churchgate`.
- **Impact:** (a) the Explore area dropdown is unusable/embarrassing; (b) selecting an area silently drops sibling stores; (c) the chatbot's `_extract_area` picks one arbitrary variant and `find_by_area` then misses the rest. Verified live: each JP Nagar / Electronic City variant returns only its own 1–2 stores.
- Needs area normalization/canonicalization at seed time.

### M4. 6 of 48 stores (12.5%) are invisible — no coordinates
- Stores missing `lat`/`lng`: *Sri Krishnarajendra Market, Escape Closet, Remode racks, Goodwill streets, Thrift Therapy, Flora Fountain*.
- Consequences:
  - **Never rendered on the Explore map** (`Explore.jsx:49` filters `stores.filter(s => s.lat)`).
  - **Never assigned to a zone** (`zones.py:24` drops rows without coords) → confirmed 6 stores with `zone_id = NULL`, so they never appear in any Zones-page zone.
- They still appear in list/search, so behaviour is inconsistent across pages rather than gracefully handled.

### M5. Several stores have implausible opening hours → "open now" is unreliable
- Live data surfaced stores that are "open" at 07:57 AM when almost all open at 11:00:
  - *The Preloved Co*: `open_time = "00:00"` (opens at midnight?)
  - *Sanzy Old Cloth Merchant*: `00:00–23:59` (i.e. effectively "always open")
  - *Eloutfit Thrift Store*: `open_time = "06:00"`, `close_time = None`
- `is_open_now` (`utils.py:20`) trusts these verbatim, so the "Open now" filter and the chatbot `open_now` intent return misleading results. `00:00` almost certainly means "unknown/24h" mis-parsed upstream, but nothing sanitizes it.
- Related: `is_open_now` uses server-local time with **no timezone** — on any non-IST host, "open now" is off by hours (the app is Bengaluru-only).

---

## 🟡 MINOR / POLISH

### P1. `experience_score == 0` (and any falsy score) renders as "unrated"
- `store_to_dict` (`utils.py:55`) and `chatbot._fmt_score` (`chatbot.py:123`) use `if store.experience_score` — a truthiness check that treats `0.0` as "no score". Latent (current min blended score is 1.0, verified range 1.6–4.91), but wrong and fragile. Use `is not None`.

### P2. Recommender never refits interactions/reviews at runtime
- Same root cause as C2 but broader: viewing a store logs a `view` interaction (`stores.py:62-64`) that never influences anything until restart. New reviews recompute a store's score but never re-run anomaly detection, so live reviews are never flag-checked.

### P3. Navbar can show stale auth state after logout
- Auth is module-level mutable state in `api.js`, not React state. Navbar re-renders only because `App` subscribes to `useLocation`. Logging out **while already on `/`** calls `nav('/')` (no route change) → `App` may not re-render → Navbar keeps showing the logged-in name until next navigation/refresh.

### P4. Dead import
- `StoreDetail.jsx:3` imports `{ scoreClass }` but never uses it.

### P5. "Starts under ₹X" price filter is misleading
- Both the store list (`stores.py:26`) and chatbot (`chatbot.py:307`) filter on `price_min <= X`. A store priced ₹99–₹2499 matches "under ₹200". Labelled "Starts under" so defensible, but the chatbot reply "Stores with prices starting under ₹500" over-promises given prices are entirely synthetic enrichment anyway.

### P6. Frontend bundle is one 797 kB chunk
- `three.js` + `leaflet` are bundled into a single 797 kB (221 kB gzip) JS file with no code-splitting (build warns). Landing pulls all of Three.js even though only the hero uses it. Perf/UX on slow connections.

### P7. External CDN hard dependency for the map & fonts
- `index.html` loads Leaflet CSS and Google Fonts from CDNs; `Explore`/`Zones` load CARTO tiles. The map is unusable **offline** or on a locked-down network — no local fallback for a core feature.

---

## What actually works (verified)
- Seed is idempotent and atomic; backend boots clean; no runtime 500s across all endpoints.
- Auth: register/login, PBKDF2 hashing, JWT, correct 401/409/422 status codes, malformed-token rejection.
- Review submission recomputes and persists the store score live (EcoDhaga 4.8★ → 3.59 after a 1★ review).
- Sentiment labelling (VADER), haversine `nearby`, guest fallbacks, rate limiter, CORS, `X-Response-Time`.
- Frontend builds successfully; React Router, chat UI, and store cards are wired correctly.

## Suggested fix priority
1. **C1** — re-engineer anomaly features so the planted burst is actually caught (or drop the random account-age feature); it poisons every score. *(highest ROI — it's the product's core claim)*
2. **C2** — refit/incrementally update the recommender after writes, or compute recs on demand, so real users get personalization.
3. **M1** — one-line regex fix (`zones?`) restores a documented flagship query.
4. **M3 / M4 / M5** — clean the store dataset (canonical areas, backfill coords, sanitize hours). Fixes filtering, the map, and zones together.
5. **M2** — retune zone labelling so the four advertised archetypes actually appear.

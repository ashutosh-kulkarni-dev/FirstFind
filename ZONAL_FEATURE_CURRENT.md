# Zonal Feature — Current Technical Behaviour

**Purpose of this doc:** describe exactly what the "Thrift Zones" feature does
today, end to end, as built — not what it should do. Read it, then tell me the
changes you want and I'll turn them into an execution plan.

Grounded against the live dev DB (`app/backend/thriftfind.db`): 48 stores with
coordinates, 4 zones, every coordinate-bearing store assigned to exactly one
zone.

---

## What the feature is, in one line

An offline **geographic clustering** of stores that is then **relabelled by
price/review rank** into four fixed marketing archetypes (Budget / Premium /
Hidden Gem / Mixed), surfaced on a map, on a cards page, in the chatbot, and as
one input feature to the recommender.

The important tension is in that sentence: the clusters are formed from
*geography*, but the names are assigned from *price and review counts*. Those two
things are not the same axis. See "Why it may feel like it has no effect" below.

---

## Data flow (where zones come from and where they go)

```
seed.py  (or pipeline.recompute_zones)
   │
   │  rows = [{id, lat, lng, price, score, review_count}]  ← coordinate stores only
   ▼
zones.cluster_stores(rows)                         app/backend/app/ml/zones.py
   │   1. keep stores with lat AND lng (others are "hidden", never zoned)
   │   2. StandardScaler on (lat,lng) → Xgeo
   │   3. HDBSCAN over Xgeo, sweeping min_cluster_size 4..n/3,
   │      take first result with 2..N_ZONES clusters
   │        └─ noise points (-1) reattached to nearest cluster centroid
   │   4. if HDBSCAN never yields 2..N_ZONES clusters → KMeans(N_ZONES) fallback
   │      (KMeans uses lat,lng weighted ×2 + price ×0.8 + score ×0.5)
   │   5. per-cluster stats: center = mean(lat,lng), avg_score, avg_price, avg_reviews
   │   6. RANK-BASED LABELLING (forced, unique):
   │        Premium   = cluster with max avg_price
   │        Budget    = cluster with min avg_price
   │        Hidden Gem= cluster with min avg_reviews (of those left)
   │        Mixed     = everything else
   ▼
returns [{label, center_lat, center_lng, store_ids, avg_score, avg_price, description}]
   │
   ▼
seed.py writes Zone rows + sets Store.zone_id                app/backend/app/seed.py:155-170
   │
   ├──► GET /api/zones            → Zones.jsx map + cards      app/backend/app/routers/misc.py:23
   ├──► chatbot "zone_exploration" intent                     app/backend/app/ml/chatbot.py:447
   └──► recommender one-hot zone feature                      app/backend/app/ml/recommender.py:92
```

---

## Component-by-component

### 1. Clustering — `app/backend/app/ml/zones.py`

- **Algorithm:** HDBSCAN (density-based) over standardized `(lat, lng)` only —
  price and score do **not** influence the primary clustering. It sweeps
  `min_cluster_size` from 4 up to `n/3` and accepts the **first** configuration
  that produces between 2 and `N_ZONES` (=4) clusters (`zones.py:38-43`).
- **Noise handling:** HDBSCAN's noise points (label `-1`) are re-attached to the
  nearest cluster centroid so every store lands in a zone (`zones.py:46-52`).
  This is deliberate ("leaving a third of stores zoneless hurts UX"), but it
  means the "cluster" boundaries are softer than density clustering implies.
- **Fallback:** if HDBSCAN can't find 2..4 clusters, `KMeans(N_ZONES)` runs — and
  KMeans *does* fold price (×0.8) and score (×0.5) into the feature space
  alongside geography (×2 each) (`zones.py:55-64`). So the clustering *basis
  silently differs* depending on which path fired. There's no record in the DB of
  which one produced the current zones.
- **`N_ZONES = 4`** is fixed in `config.py:73`. HDBSCAN is capped at 4; the
  labelling step assumes up to 4 archetypes. The "density finds however many
  clusters the data supports" claim in the module docstring is bounded to ≤4 in
  practice.

### 2. Labelling — the semantic core (and the weak point)

After clusters exist, they are named by **rank, not by meaning** (`zones.py:98-114`):

| Label | Rule |
|---|---|
| Premium Zone | cluster with the highest `avg_price` |
| Budget Zone | cluster with the lowest `avg_price` |
| Hidden Gem Zone | of the remaining, the one with the fewest `avg_reviews` |
| Mixed Zone | whatever is left |

Consequences:
- The four names **always** appear (when there are 4 clusters), regardless of
  whether the data actually has a distinctly premium or budget area. One cluster
  is *by definition* "Premium" even if its average price is barely above the
  others'.
- Labels are assigned to **geographic** clusters. So "Premium Zone" means "the
  geographic blob that happened to have the highest mean price," not "a
  coherent premium shopping district." A single expensive store can tip a
  geographic cluster into the "Premium" name.
- The label is **unique by construction** — exactly one of each — so it carries
  no information beyond the rank ordering of 4 blobs.

### 3. Storage — `app/backend/app/models.py:78`

`Zone` table: `id, label, center_lat, center_lng, store_count, avg_score,
avg_price, description`. `Store.zone_id` (`models.py:48`) is a plain nullable
`Integer` — **not a foreign key**, no relationship object. Stores without
coordinates keep `zone_id = NULL` and never appear in any zone.

The zone stores only a **centroid point** — no radius, no bounding box, no
polygon, no member-extent. The geographic *shape* of a zone is not persisted.

### 4. API — `GET /api/zones` — `app/backend/app/routers/misc.py:23`

Returns every zone with its stats plus `top_stores` = the 3 highest
`experience_score` stores in that zone. No filtering, no query params, no
pagination. Pure read of precomputed rows.

### 5. Frontend — `app/frontend/src/pages/Zones.jsx`

- Leaflet dark map centred on Bengaluru (`12.9716, 77.5946`, zoom 12).
- For each zone it draws a **fixed-radius circle of 2200 m** at the centroid
  (`Zones.jsx:34`). This radius is **hard-coded and identical for every zone** —
  it is not derived from the cluster's actual spread. A tight 8-store cluster and
  a sprawling 18-store cluster get the same 2.2 km circle. Circles can overlap or
  under/over-cover the real member positions.
- Below the map, one card per zone: label, store_count, avg_score, avg_price,
  description, and up to 3 `top_stores` (via `StoreCard`).
- **Doc drift:** the page's own subtitle says *"K-Means clustering over location,
  price, and experience score"* (`Zones.jsx:43-44`). That describes the *fallback*
  path, not the primary HDBSCAN-on-geography-only path that normally runs.

### 6. Chatbot — `zone_exploration` intent — `app/backend/app/ml/chatbot.py:447`

- Triggered by regex on words like `zone(s)`, `neighbourhood`, `hidden`,
  `market`, `which part` (`chatbot.py:51`).
- If the query contains "hidden"/"know" → returns the Hidden Gem zone + its top 4
  stores. If "budget"/"cheap"/"affordable" → Budget zone + top 4. Otherwise →
  a bullet list of all zones with stats and a nudge to the Zones page
  (`chatbot.py:450-467`).
- Only "hidden" and "budget" are routable by keyword; there is **no** keyword
  path to reach the Premium or Mixed zones specifically.

### 7. Recommender — `app/backend/app/ml/recommender.py:92`

`zone_id` is folded into the content feature vector as a **one-hot** dimension
alongside categories, price band, and quality (`recommender.py:86-109`). This is
the only place zones affect anything beyond display. Because the one-hot is just
an opaque cluster id, two stores in the same geographic blob are nudged "similar"
regardless of whether they're actually alike.

---

## Current live state (dev DB)

| id | label | stores | avg_score | avg_price | centroid |
|---|---|---|---|---|---|
| 1 | Hidden Gem Zone | 8 | 4.47 | ₹583 | 13.0155, 77.6460 |
| 2 | Budget Zone | 11 | 3.95 | ₹424 | 12.9716, 77.5785 |
| 3 | Mixed Zone | 18 | 3.86 | ₹512 | 12.9025, 77.6162 |
| 4 | Premium Zone | 11 | 4.09 | ₹1499 | 12.9482, 77.6020 |

48/48 coordinate stores are zoned. Note the price spread: Budget ₹424 →
Premium ₹1499 is driven largely by the Premium cluster's mean — the middle three
zones (₹424 / ₹512 / ₹583) are close together, so "Budget" vs "Hidden Gem" vs
"Mixed" is a thin distinction in practice.

---

## Why it may feel like it "has no effect"

Observations only — not recommendations. These are the mechanical reasons the
feature reads as inert:

1. **It's almost entirely read-only display.** Outside the recommender's one-hot,
   nothing in the app *behaves* differently because of zones. There is no
   "filter by zone," no "stores near this zone," no routing/navigation, no map
   interaction beyond a popup. It informs; it does not act.

2. **Labels are geographic clusters wearing price/review names.** A user reading
   "Premium Zone" expects a curated premium district; they get "the blob with the
   highest average price," which may be one pricey store away from being "Mixed."
   The name promises a semantic that the clustering doesn't deliver.

3. **The archetypes are forced, so they're low-information.** Exactly one of each
   label always exists. The feature can never say "this city has no real budget
   cluster" or "there are two premium pockets" — the ranking manufactures the
   four names every time.

4. **The map geometry is cosmetic.** Fixed 2200 m circles at centroids don't
   represent the true extent or density of each cluster, so the map doesn't let
   you reason about *where* a zone actually is or how big it is.

5. **The clustering basis is unstable/opaque.** HDBSCAN (geo-only) vs KMeans
   (geo+price+score) can both produce the "current" zones, with no persisted
   marker of which ran. Re-seeding could shift both membership and meaning.

6. **Discovery is thin in the chatbot.** Only Budget and Hidden Gem are directly
   reachable by keyword; Premium/Mixed are only listed.

---

## Files that define the feature

| File | Role |
|---|---|
| `app/backend/app/ml/zones.py` | clustering + labelling (the whole algorithm) |
| `app/backend/app/config.py:72-74` | `CITY_CENTER`, `N_ZONES=4`, `SEED=42` |
| `app/backend/app/models.py:48,78` | `Store.zone_id`, `Zone` table |
| `app/backend/app/seed.py:155-170` | writes zones + assigns `zone_id` at seed |
| `app/backend/app/ml/pipeline.py:55-81` | `recompute_zones()` (recluster on refresh) |
| `app/backend/app/routers/misc.py:23-36` | `GET /api/zones` |
| `app/backend/app/ml/chatbot.py:447-469` | `zone_exploration` intent |
| `app/backend/app/ml/recommender.py:86-109` | zone as a one-hot content feature |
| `app/frontend/src/pages/Zones.jsx` | map + cards UI |
| `app/frontend/src/App.jsx:22`, `Navbar.jsx:14` | route + nav link |

---

*Next step:* mark up this doc with the changes you want (relabelling logic, map
geometry, zone-based filtering, chatbot coverage, clustering basis, etc.) and
I'll convert it into a phased execution plan like `LOCATION_SEARCH_PLAN.md`.

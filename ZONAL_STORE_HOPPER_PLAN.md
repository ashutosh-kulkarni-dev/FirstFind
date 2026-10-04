# Shopping Zones (Store-Hopper) — Execution Plan

**Status:** proposed (awaiting approval). No code changes until approved.
**Supersedes:** the price-archetype zone model documented in
`ZONAL_FEATURE_CURRENT.md`.
**Scope:** redefine "zones" as geographic store-hopper clusters; wire them into
the conversational chatbot; add a standalone, parameterized cluster finder.

---

## The reframe, in one line

A zone stops being *"the geographic blob that averaged the highest price"* and
becomes *"a pocket of Bengaluru where several thrift stores sit close enough to
walk between — a place to spend an afternoon."*

Naming moves from **price/review rank** (Budget / Premium / Hidden Gem / Mixed)
to **geography** ("Indiranagar & around", "SG Palya cluster"). That is the whole
point of the change and everything below follows from it.

### Why drop the price/review labels (your reasons, made concrete)

1. **Price is not universal.** Not every store has `price_min/price_max`
   (`_soft_excluded` at `chatbot.py:268` already treats blank price as "keep,
   don't judge"). Labelling a whole *area* "Budget" or "Premium" off a partial,
   averaged signal is a guess dressed as a fact.
2. **Reviews are sparse and their absence is not a negative.** Some stores/areas
   have zero reviews. The current "Hidden Gem = fewest reviews" label
   (`zones.py:110`) quietly turns *missing data* into a *ranking*, and an
   unrated area reads as lower-quality — which deters visits to places that may
   be perfectly good. A store-hopper doesn't need a verdict; they need to know
   *where the shops are clustered.*
3. **A store-hopper optimizes distance, not price tier.** The valuable question
   is "where can I hit 5 shops without a long commute between each?" Coordinates
   answer that; price averages don't.

So: **cluster on geography, name by geography, rank by proximity, never gate on
price or reviews.** Price/rating stay as *displayed* facts on each store card,
never as the zone's identity or a filter.

---

## Reconciling with the locked chatbot principles

`CHATBOT_RETRIEVAL_PLAN.md` locks: **token-free/offline retrieval**,
**hard-filter-then-rank**, and **no silent substitution (honest empty)**. This
plan keeps all three:

- **Token-free:** clustering + haversine are pure Python/NumPy. The LLM only
  rephrases the final draft, exactly as today (`chatbot.py:548`).
- **Hard-filter-then-rank:** the radius is the hard filter (store is in the zone
  or it isn't); proximity + existing `_relevance()` only *order* within it.
- **Honest empty:** if a location has fewer than the requested number of stores
  in the radius, we say so and **offer to widen the radius** — we never quietly
  pad the cluster with far-away stores. This mirrors the existing
  "I don't have any stores listed in {location} yet" behaviour (`chatbot.py:414`).

---

## Target design — one primitive, two modes

Everything rests on a single new function (proposed home:
`app/backend/app/ml/clusters.py`):

```
find_cluster(center=(lat,lng), radius_km, min_shops, *, open_now=False,
             category=None, day=None) -> Cluster
discover_clusters() -> list[Cluster]     # the "natural pockets" for the default view
```

A **Cluster** is honest and geography-first:

```
{
  name:        "Indiranagar & around",   # dominant area/locality of members
  center_lat, center_lng,
  radius_km:   1.6,                       # ACTUAL extent, not a fixed 2200 m
  store_count: 7,
  walkable:    true,                      # radius <= WALKABLE_KM (~1.2)
  store_ids:   [...],
  stores:      [store_dict, ...],         # proximity-ordered; price/rating shown, not ranked-on
  avg_score:   4.1                        # displayed as a soft signal ONLY (may be null)
}
```

### Mode A — Discovery (global, precomputed): "where do I go thrifting?"

Reuse the existing HDBSCAN-on-geography primitive (`zones.py:33-52`) — it already
finds density-based geographic clusters; that part was always right. We **strip
the price/review relabelling** (`zones.py:98-114`) and instead:

- name each cluster by the **dominant `area` / `locality_raw`** of its members;
- compute a **real radius** = the distance from the centroid to its farthest
  member (or the 90th-percentile distance, to shrug off one outlier);
- keep noise-reattachment so no store is orphaned (`zones.py:46-52`).

This is what the chatbot lists when no location is given, and what the standalone
page shows by default. No forced count of 4, no forced archetypes.

### Mode B — Personalized (on-demand, live): "find me a cluster near X"

Given a center + radius + target count, return the stores inside the radius,
proximity-ordered. **This is almost entirely already built:**
`GET /api/stores/nearby?lat&lng&radius_km` (`stores.py:64-75`) does the haversine
radius search and distance-sorts. The new work is only:

- resolve a **typed/dropdown location → (lat,lng)** (see "Location resolution");
- apply `min_shops` with an **honest-empty + widen-radius** response;
- attach the cluster name + walkability;
- (optional) order the stores as a **walking route** (nearest-neighbour path).

---

## Location resolution (how "input a location" works without a new gazetteer)

The standalone dropdown and the chatbot both need `location string → (lat,lng)`.
We get this **for free today**, no `geo.py`/gazetteer required for v1:

- **Dropdown / known areas:** each area's centroid = mean of its member stores'
  coords. Every area in `/api/stores/areas` (`stores.py:45`) thus has a
  coordinate with zero new data. This covers the dropdown completely.
- **Free-text in chat:** reuse `_extract_area()` (`chatbot.py:120`) →
  area centroid; on miss, `_extract_locality_phrase()` (`chatbot.py:148`) →
  centroid of the matching stores. Both already exist and are offline.
- **Browser geolocation (optional):** the standalone page can pass the user's GPS
  `(lat,lng)` straight in as the center — no resolution needed.
- **Upgrade path (later):** arbitrary localities not tied to any store need the
  offline gazetteer from `LOCATION_SEARCH_PLAN.md` Phase 3. Call it out as the
  v2 enabler; **v1 does not depend on it.**

---

## Chatbot integration (rewrite the `zone_exploration` intent)

Today `zone_exploration` (`chatbot.py:447-469`) only routes to Budget/Hidden by
keyword and lists price-labelled zones. Rewrite it around the primitive:

1. **Trigger** stays regex + fuzzy (`chatbot.py:51,65`), broadened for store-
   hopper phrasing: `crawl`, `hop`, `spend the day`, `shops near`, `cluster`,
   `walkable`, `area to thrift`.
2. **Parse params from the message** (all token-free regex, like `_extract_price`
   at `chatbot.py:189`):
   - location → `_extract_area` / `_extract_locality_phrase` (existing);
   - radius → `within N km` / `N km radius` (default `LOCATION_RADIUS_KM`, already
     in `config.py`);
   - count → `at least N` / `N shops` / `N stores`.
3. **Route:**
   - **location present →** Mode B: `find_cluster(area_centroid, radius, count)`.
     Reply: *"Around Koramangala there are 6 thrift stores within 2 km — here's a
     walkable loop:"* + proximity-ordered stores. If `count` not met: *"Only 3
     within 2 km. Want me to widen to 4 km?"* (honest empty, offer to widen).
   - **no location →** Mode A: list the natural clusters by name + store count +
     walk radius: *"The densest thrift pockets right now: Indiranagar (7 shops,
     ~1.5 km), SG Palya (5, ~1 km)… Ask about any, or open the Shopping Zones
     page."*
4. **Return contract unchanged:** still `{reply, intent, stores, suggestions}`
   (`chatbot.py:550`), so the LLM phrasing step (`chatbot.py:548`) and the
   frontend need no shape change. `stores` carries the cluster members;
   `_build_context` (`chatbot.py:346`) already ships per-store facts to the LLM —
   we just stop sending the price-archetype `zone` label and send the geographic
   cluster name instead.
5. **Update `SUGGESTIONS`** (`chatbot.py:72`) and the greeting/general copy
   (`chatbot.py:401,537`) away from "budget thrift zones" toward
   "a thrift crawl near you / walkable shopping pockets."

---

## Standalone feature (parameterized cluster finder)

### API

`GET /api/clusters` — Mode A, the natural pockets (default page load).

`GET /api/clusters/find?location=<area>|lat=&lng=&radius_km=2&min_shops=5&open_now=&day=&category=`
— Mode B. Returns one (or a few candidate) `Cluster` objects. Built on the
existing `nearby` logic (`stores.py:64`); add `min_shops` + naming + optional
route order. Add both to `api.js` (`api.clusters`, `api.findCluster`).

### UI (rework `app/frontend/src/pages/Zones.jsx` → "Shopping Zones")

Controls the customer can set (your two, plus proposed additions):

| Control | Values | Notes |
|---|---|---|
| **Location** | dropdown of areas **+** "Use my location" (GPS) **+** free-text | dropdown from `/api/stores/areas`; GPS via `navigator.geolocation` |
| **Radius** | 1 km / 2 km / 3 km / 5 km (or slider) | default `LOCATION_RADIUS_KM` = 2 |
| **Min shops** | 3 / 5 / 8 / "as many as possible" | drives honest-empty + widen prompt |

Map: draw the cluster as a circle of its **actual** radius (fixes the hard-coded
2200 m at `Zones.jsx:34`), pin **every member store** (not just a popup), and —
if route ordering is on — draw the walking path between pins in order. Cards below
list the stores proximity-ordered with distance from center.

Fix the stale copy: the page subtitle still says *"K-Means clustering over
location, price, and experience score"* (`Zones.jsx:43`) — replace with the
store-hopper framing.

---

## More personalization ideas (you asked me to extend the list)

Ranked by value-per-effort for a store-hopper. Pick which to include; each is
additive and optional.

1. **Thrift-crawl route + ETA (high value).** Order the cluster's stores as a
   nearest-neighbour walking path from the center and show total walking distance
   and rough time. Turns "here are 6 shops" into "here's your afternoon, in
   order." Pure geometry on coords you already have.
2. **"Open that day/now" filter (high value, low effort).** Reuse
   `is_open_now()` (`utils.py:53`) and `closed_days` so a Saturday plan excludes
   Monday-closed shops. Soft by default (unknown hours are kept, per existing
   policy) so sparse-hours stores aren't hidden.
3. **Transport presets (low effort).** "Walking" → 1 km, "Auto/bike" → 3–5 km —
   a friendlier front end over the radius control.
4. **Start from my GPS (medium).** Browser geolocation as the center → "shops I
   can hop to from where I am right now."
5. **Category lean (medium).** Bias/annotate the cluster toward a requested
   category ("vintage-heavy pocket") — soft only, since many stores list none
   (blank stays in, per `_soft_excluded`).
6. **Biggest vs closest (low).** When several clusters qualify, let the user pick
   "most shops" vs "nearest to me."
7. **Shareable / saveable crawl (medium).** A share link or "save this crawl" to
   the profile — the natural unit for a group thrift outing.
8. **Density heat, not just circles (later).** Show relative store density so the
   map communicates *where the scene actually is.*

Explicitly **not** doing: any price-tier or minimum-rating gate — that
reintroduces exactly the deterrent you're removing. Rating can be an optional,
default-**off** soft sort at most.

---

## File-by-file change list

| File | Change |
|---|---|
| `app/backend/app/ml/clusters.py` *(new)* | `find_cluster()`, `discover_clusters()`, route-ordering + naming helpers. Reuses `zones.py`'s HDBSCAN primitive and `utils.haversine_km`. |
| `app/backend/app/ml/zones.py` | Keep the geographic clustering (`_hdbscan_labels`, `_reattach_noise`); **remove** the price/review relabelling (`zones.py:98-114`) and `ZONE_DESCRIPTIONS`; return geography-named clusters with a real radius. |
| `app/backend/app/models.py` | `Zone`: replace price-archetype semantics — drop reliance on `avg_price`; add `radius_km` (Float) and rename intent of `label` to the geographic name. (`avg_score` may stay as a displayed soft field.) |
| `app/backend/app/seed.py` (`155-170`) + `pipeline.py` (`recompute_zones`, `55-81`) | Write geography-named clusters + `radius_km`; drop avg_price-driven labelling. |
| `app/backend/app/ml/chatbot.py` | Rewrite `zone_exploration` (`447-469`) around `find_cluster`/`discover_clusters`; add radius/count regex extractors; broaden triggers (`51,65`); refresh `SUGGESTIONS` + copy (`72,401,537`); send cluster name not price label in `_build_context` (`350,363`). |
| `app/backend/app/routers/misc.py` | Repoint `GET /api/zones` to the new discovery output; **or** add `GET /api/clusters` + `GET /api/clusters/find`. |
| `app/backend/app/routers/stores.py` | Optionally factor the radius search out of `nearby` (`64-75`) so `find_cluster` and the endpoint share it. |
| `app/backend/app/config.py` | Add `WALKABLE_KM = 1.2`, `MAX_RADIUS_KM = 5.0`; reuse existing `LOCATION_RADIUS_KM`. |
| `app/frontend/src/api.js` | Add `clusters()` / `findCluster(params)`. |
| `app/frontend/src/pages/Zones.jsx` | Rework to the parameterized finder (location/radius/min-shops controls, actual-radius circle, per-store pins, optional route); fix stale copy. |

---

## Execution phases (each independently shippable + verifiable)

1. **Reframe discovery (Mode A).** Strip price/review labels in `zones.py`; name
   clusters by geography; compute real radius; re-seed. `/api/zones` now returns
   honest geographic pockets. Frontend copy + actual-radius circle. *Lowest risk;
   ships the conceptual change with no new endpoint.*
2. **Chatbot integration.** Rewrite `zone_exploration` to list Mode-A pockets and,
   when a location is named, do a live radius cluster with honest-empty + widen.
   *This is the "part of the conversational feature" you asked for.*
3. **Standalone finder (Mode B).** `GET /api/clusters/find` (built on `nearby`);
   the parameterized UI (location dropdown/GPS, radius, min-shops); per-store pins.
   *Delivers the standalone, personalized feature.*
4. **Personalization add-ons.** Route ordering + ETA, open-that-day filter,
   transport presets, share/save — from the ranked list above, in your priority.

Recommendation: **1 → 2** delivers the store-hopper reframe inside the chatbot
(your primary ask). **3** adds the standalone tool. **4** is polish.

---

## Verification (extend `app/backend/_verify.py`)

Token-free, SQLite, no network. New assertions:

- **Geographic naming:** every returned cluster's name matches a real member
  `area`/`locality_raw`; no cluster is named "Budget/Premium/Hidden/Mixed".
- **No price/review gate:** a cluster includes stores with `price_min = NULL` and
  with `review_count = 0` (proves unpriced/unreviewed shops aren't deterred).
- **Radius is the hard filter:** every store in a Mode-B cluster is within
  `radius_km` of the center; none outside leaks in.
- **Honest empty + widen:** a location with `< min_shops` in radius yields the
  honest reply and a widen suggestion — not padded with far stores.
- **Real radius:** a cluster's stored `radius_km` bounds its farthest member (no
  fixed 2200 m).
- **Chatbot round-trip:** "thrift crawl near Koramangala within 2km" returns a
  non-empty, proximity-ordered, in-radius set; "where should I go thrifting?"
  lists geographic pockets.
- **Zero-network:** monkeypatch network to raise; both modes still work.

---

## Risks & mitigations

1. **Location without coords can't anchor a cluster.** Areas whose stores lack
   coords have no centroid. *Mitigation:* dropdown is built from
   `/api/stores/areas` (coord-backed only, `stores.py:45`); free-text misses fall
   back to the honest "I don't know that area yet" path.
2. **Sparse pockets.** Some areas have 1–2 stores — not a "cluster."
   *Mitigation:* `min_shops` + honest-empty/widen; Mode A only surfaces pockets
   meeting a floor (e.g. ≥3).
3. **Re-seed is destructive in prod (Postgres/Supabase).** Same caveat as
   `LOCATION_SEARCH_PLAN.md` Risk 2. *Mitigation:* dev re-seeds; prod gets a
   hand-written `ALTER TABLE zones ADD COLUMN radius_km …` + a backfill (no
   Alembic in repo). Note in `DEPLOYMENT.md`.
4. **Fixed radius mismatches pocket size.** *Mitigation:* Mode A computes the
   real per-cluster radius; Mode B lets the user choose it.
5. **Recompute cost.** HDBSCAN over 48 stores is trivial; live radius search is
   O(stores). Fine now; revisit a spatial index only at multi-city scale (same
   open question as `LOCATION_SEARCH_PLAN.md` Risk 5).

---

## Decisions I need from you

1. **Keep a precomputed cluster table, or go fully live?** Recommendation: keep a
   small precomputed set for Mode A (fast, stable default) + live Mode B. The
   alternative (no table, cluster on every request) is simpler but recomputes each
   call. Your call changes whether `Zone` survives as a table.
2. **How many pockets should Mode A show, and the minimum stores to count as a
   pocket?** (Was a forced 4; I'd make it dynamic with a floor of ~3.)
3. **Which personalization add-ons (section above) are in v1 vs later?**
4. **Route ordering: in scope for the first standalone ship, or a fast-follow?**

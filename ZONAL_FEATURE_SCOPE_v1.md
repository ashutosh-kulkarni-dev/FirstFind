# Zonal Feature — Scope v1 (LOCKED)

**Status:** approved for build. Supersedes the six review files in
`docs/feature-feasibility/` for everything concerning the **zonal / map**
surface. Chatbot travel-time, traffic, and metro *routing* are explicitly out of
this doc — see `CHATBOT_ENHANCEMENTS_NEXT_STAGE.md`.

**Grounded against:** `ZONAL_STORE_HOPPER_PLAN.md`, `ZONAL_FEATURE_CURRENT.md`,
`LOCATION_SEARCH_PLAN.md`, `BACKEND_OVERVIEW.md`. Stack: FastAPI + SQLAlchemy,
HDBSCAN geo-clustering (`ml/zones.py`), haversine radius search
(`GET /api/stores/nearby`, `utils.haversine_km`), Leaflet frontend (`Zones.jsx`),
offline / token-free retrieval principle.

---

## 1. What v1 is, in one line

A **map-distance, interactive, editable geographic cluster** the user drives:
they pick a zone, the app shows the walkable pocket of shops inside it, and they
can drag the cluster, resize the radius, and tighten/loosen how many shops it
holds — live. No traffic. No travel-time. No administrative boundaries.

---

## 2. Locked decisions

| # | Decision | Value | Source |
|---|---|---|---|
| D1 | Radius meaning | **Haversine map distance** (crow-flies). Not road, not travel-time. | file 02 |
| D2 | Default radius | **2 km** (`config.LOCATION_RADIUS_KM`) | file 02 |
| D3 | Radius bands | Walkable ≤2 / Scooter 3–6 / Macro 7–10 km | file 02 |
| D4 | Radius UI | **All three on one value:** named band buttons + free slider (0–10) + text input | file 02 |
| D5 | `min_shops` default | **3** | file 01 |
| D6 | `max_shops` (cap) default | **8** | file 01 |
| D7 | Discovery pocket floor | **3** (Mode A won't surface pockets < 3 shops) | file 01 |
| D8 | Cap behaviour | **Show all + "too many — tap to split" prompt.** On tap, sub-cluster into named sub-zones ≤ cap. Never silently truncate. | file 01 (#3=b, reconciled) |
| D9 | `min_shops = 1` | "Solo Gem" = **no density filter**. No special data flag (none exists). | file 01 (#4=no) |
| D10 | One-Tap Presets | **IN.** Named bundles of `{min_shops, max_shops, radius_km}`. | file 04 (#1=yes) |
| D11 | Neighborhood Snap | **OUT.** No ward polygons, no area-hulls. Cluster stays a real-radius circle. | file 06 (#2=no) |
| D12 | Cluster interactivity | Cluster **starts from the user's chosen zone**; user can **drag** it and **live-edit** its params. | file 06 |
| D13 | Compute split | **Client-side live preview** while dragging/editing; **server is authoritative** on commit/save. Minor preview↔commit drift accepted. | file 06 (interactivity) |
| D14 | Metro | **Overlay only** (proximity: how near shops are to stations), Purple + Green lines. Metro *routing* is chatbot-stage, not here. | file 04 (#4=yes) |
| D15 | Traffic / travel-time | **OUT of zonal entirely.** Chatbot-stage only. | files 02/03 |
| D16 | Circle geometry | Replace the hard-coded **2200 m** circle (`Zones.jsx:34`) with each cluster's **real radius** (farthest member, or 90th-percentile to shrug off one outlier). | plan |

---

## 3. The Cluster object

The single primitive everything returns. Geography-first, honest, no price/review
identity (the old Budget/Premium/Hidden/Mixed labelling is removed per
`ZONAL_STORE_HOPPER_PLAN.md`).

```
Cluster {
  name:         "Indiranagar & around",   # dominant area/locality_raw of members
  center_lat, center_lng,                 # editable — user can drag this
  radius_km:    1.6,                       # REAL extent (D16), editable via slider
  min_shops:    3,                         # editable
  max_shops:    8,                         # editable; drives the split prompt (D8)
  store_count:  7,
  walkable:     true,                      # radius <= WALKABLE_KM (~1.2)
  over_cap:     false,                     # true → frontend shows "tap to split"
  sub_zones:    [] | [Cluster, ...],       # populated after a split
  store_ids:    [...],                     # proximity-ordered from center
  stores:       [store_dict, ...]          # price/rating shown as facts, never filtered on
}
```

---

## 4. Interaction model (the heart of v1)

1. **Start from a zone.** User selects an area (dropdown from `/api/stores/areas`,
   already coord-backed) or uses "my location" (browser GPS). That point becomes
   the cluster center.
2. **See the pocket.** App draws the real-radius circle + a pin per member store,
   cards below proximity-ordered with distance from center.
3. **Drag the center.** Moving the circle re-runs the in-radius filter **client-
   side** (D13) for instant feedback; pins/cards update live.
4. **Edit radius.** Band button / slider / text (D4) resizes the circle live.
5. **Edit density.** `min_shops` / `max_shops` adjust live:
   - below `min_shops` in radius → **honest empty + "widen radius?"** (never pad
     with far shops — respects the no-silent-substitution principle).
   - above `max_shops` in radius → `over_cap = true` → **"too many — tap to
     split"** prompt (D8).
6. **Split on tap.** Sub-cluster the in-radius set (HDBSCAN at a tighter
   `min_cluster_size`, reusing the `zones.py` primitive) into named sub-zones each
   ≤ `max_shops`; render them as separate circles.
7. **Commit.** On release/save, the frontend calls the server, which returns the
   **authoritative** cluster (server HDBSCAN + real radius + geographic name). The
   live preview is replaced by the committed result.

---

## 5. Control specs

### 5.1 Radius (D1–D4)
- One state value `radius_km` ∈ [0.5, 10], default 2.
- Three synchronized surfaces: **band buttons** (Walkable→set 2 / Scooter→set 5 /
  Macro→set 9, or midpoints you prefer), **slider** (0–10, 0.5 steps), **text
  input** (clamp 0–10, reject junk).
- Circle is labelled **"map distance"** in the UI. Do not imply travel-time.
Note: Change fom radius to diameter, banglore is not easy to travel, this is mor sensible.

### 5.2 Density (D5–D9)
- `min_shops` ∈ [1, 20], default 3. `max_shops` ∈ [min_shops, 25], default 8.
- Enforcement is **filter-then-signal**, never truncate:
  - `count < min_shops` → empty state + widen CTA.
  - `min_shops ≤ count ≤ max_shops` → normal cluster.
  - `count > max_shops` → show all, set `over_cap`, offer split.
- `min_shops = 1` is exposed as an explicit **"include solo shops"** toggle so the
  user knows they've opted out of crawl density.

### 5.3 Presets (D10)
Named bundles applied on tap. Locked starter set (edit values freely):

| Preset | min | max | radius_km (diameter) |
|---|---|---|---|
| Pedestrian Crawl | 4 | 8 | 1.5 |
| Hidden Gem Hunter | 1 | 8 | 8 |
| Walkable (band) | 3 | 8 | 2 |
| Scooter (band) | 3 | 8 | 5 |
| Macro Sweep (band) | 3 | 12 | 9 |

Presets are pure frontend config — no backend. This is the cheapest high-value
item; ship it with the sliders so non-technical users can drive the controls.

---

## 6. Discovery vs personalized (two modes, one primitive)

Reuse the store-hopper plan's two modes:
- **Mode A — Discovery** (`GET /api/clusters`): precomputed "natural pockets"
  across the city, geography-named, floor of 3 shops (D7). This is the default
  view / "where do I go thrifting?" No forced count of 4, no archetypes.
- **Mode B — Personalized** (`GET /api/clusters/find?...`): the interactive
  cluster from §4, built on the existing `nearby` radius search.

---

## 7. Metro overlay (D14) — secondary layer, build after the core

- Asset: `data/metro_stations_blr.json` = `[{name, line: "purple"|"green", lat,
  lng}]`. **Purple + Green only.** Populate + hand-verify (lines have been
  extending; a stale scrape ships wrong data) — treat as a one-time curated asset,
  not a live feed.
- Behaviour in zonal: a toggle to **show station pins** and, per shop/cluster, a
  **"~N m from <station>"** proximity label (haversine to nearest station). "Shops
  near <station>" = station coord as a Mode-B center.
- Out of scope here: "best metro route from my start" (that's routing over the
  line graph → chatbot doc).

---

---

---

## 10. Build order (each independently shippable + verifiable)

1. **Core reframe + real radius.** Strip price/review labels in `zones.py`;
   geographic naming; real per-cluster radius; `/api/clusters` (Mode A). Frontend:
   real-radius circle + copy fix. *Lowest risk; ships the conceptual change.*
2. **Interactive Mode B.** `GET /api/clusters/find`; the parameterized UI
   (location/GPS, radius band+slider+text, min/max); per-store pins; honest-empty
   + widen. *Delivers the core user-driven cluster.*
3. **Drag + live edit + presets.** Client-side preview on drag/param-change;
   preset buttons; commit-to-server. *The "feels alive" layer.*
4. **Cap split.** `over_cap` detection + "tap to split" + `split_cluster()` into
   named sub-zones. *Reuses the same primitive.*
5. **Metro overlay.** Populate `metro_stations_blr.json`; station pins + proximity
   labels; "shops near <station>." *Additive; after the core is solid.*

---

## 11. Verification (extend `app/backend/_verify.py` — token-free, SQLite, no network)

- **Geographic naming:** every cluster name matches a real member
  `area`/`locality_raw`; none named Budget/Premium/Hidden/Mixed.
- **No price/review gate:** a cluster includes stores with `price_min = NULL` and
  `review_count = 0`.
- **Radius is the hard filter:** every store in a Mode-B cluster is within
  `radius_km`; nothing outside leaks in.
- **Honest empty + widen:** `< min_shops` in radius → honest reply + widen
  suggestion, not padded.
- **Cap → split, not truncate:** `> max_shops` yields `over_cap=true` and, on
  split, sub-zones each ≤ `max_shops` whose union = the original in-radius set (no
  shop dropped).
- **Real radius:** stored `radius_km` bounds the farthest member (no fixed 2200 m).
- **Metro proximity:** each shop's nearest-station distance is the true haversine
  min over the station asset.
- **Zero-network:** monkeypatch network to raise; all modes still work.

---

## 12. Assumptions & accepted risks

1. **Coordinates deferred (your call).** You're updating many coords later. v1 is
   built to be correct; **at ~48 stores the density features will look sparse in
   demo** (min 3–4 in a 1.5 km circle will often be honest-empty). This is a data
   state, not a bug — the honest-empty + widen UX is designed for exactly it.
   [Certain] no code fixes this; only catalogue growth + coord accuracy does.
2. **Scale.** Client-side live clustering + brute-force haversine are trivial at
   tens–hundreds of stores. Revisit a spatial index (PostGIS `ST_DWithin` /
   geohash) only at multi-city / thousands scale.
3. **Preview↔commit drift (D13).** Client preview may differ slightly from the
   server's authoritative cluster on commit. Accepted; the committed result wins.
4. **Metro asset staleness.** Station list is a curated snapshot; note a review
   cadence when lines change.

---

## 13. Micro-decisions defaulted (override anytime)

- Band-button target values (§5.1): Walkable→2, Scooter→5, Macro→9 km.
- Split algorithm: HDBSCAN at reduced `min_cluster_size`; if it can't split, fall
  back to KMeans(k = ceil(count/max_shops)).
- Cluster name source: dominant `area`, tie-break to `locality_raw`.
- These are set so the build isn't blocked; change the numbers freely.

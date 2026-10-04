# Zonal Feature v1 — Implementation Plan

**Status:** plan only — no code written yet. Derived from `ZONAL_FEATURE_SCOPE_v1.md`
(LOCKED) and grounded against the actual codebase.

**Decisions taken (owner):**
- **In-place reframe** (not a parallel module). Archetypes removed everywhere in Phase 1.
- **Extend the existing `Zone` table** (add one column) — do not create a new table.
- **New area-centroids endpoint** to give Mode B a start point.
- The **`Zone` table is the single source of truth**; both the zonal map and the
  chatbot read the same rows. It must be perfected before either consumer changes.

---

## 0. Guiding principles
- **One source of truth = the `Zone` table.** Rows are geography-named clusters with a
  real radius. Both the zonal map and the chatbot's `zone_exploration` read from it via
  one shared serializer. No feature re-derives clusters independently.
- **Zones are boundary-free.** A `Zone` row is `center + radius_km`, nothing more.
  Mode B searches by coordinate + radius and ignores which zone a point "belongs" to,
  so a small place *inside* a zone works exactly like any other center (see §7, Q1).
- **Radius is the only hard filter.** Price/review never gate membership; they remain
  displayed facts.
- **Token-free / offline**, matching `_verify.py` (SQLite, network monkeypatched to raise).

---

## 1. The new `Zone` contract (freeze this first)

**Model — `app/backend/app/models.py` (Zone):**
| Field | Change |
|---|---|
| `label` | Now the **geographic name** (dominant member `area`, tie-break `locality_raw`). Widen to `String(120)`. |
| `radius_km` | **NEW** `Column(Float)` — real extent (90th-percentile haversine from centroid to members, D16). |
| `avg_price` | **Keep column**, displayed *fact only* — never identity, never a filter. |
| `avg_score` | Keep as displayed soft field. |
| `center_lat/lng`, `store_count`, `description` | Keep. `description` = neutral geographic blurb (no archetype copy). |

`min_shops` / `max_shops` / `over_cap` / `sub_zones` from the doc's Cluster object are
**Mode-B API concerns, not persisted columns** — keeps the schema change to one column.

**Canonical serializer:** add `zone_to_dict(zone, stores=None)` to `utils.py` (beside
`store_to_dict`). `/api/zones`, `/api/clusters`, and the chatbot all emit through it.
This is the single-source-of-truth guarantee at the serialization layer.

---

## 2. Phase 1 — Core reframe + real radius + BOTH consumers reconciled
*Ships the conceptual change. Nothing interactive yet. This is the phase the
single-source-of-truth constraint is about — the chatbot changes here, not later.*

**`config.py`** — add `WALKABLE_KM = 1.2`, `MAX_RADIUS_KM = 10.0`,
`DEFAULT_MIN_SHOPS = 3`, `DEFAULT_MAX_SHOPS = 8`, `POCKET_FLOOR = 3`.
Reuse `LOCATION_RADIUS_KM = 2.0`.

**`ml/zones.py`** — strip identity, keep geography:
- Delete `ZONE_DESCRIPTIONS` and the rank-based relabel block (lines 98–127).
- Remove price/score features from the fallback; `_kmeans_labels` becomes geography-only
  (or drop it if HDBSCAN + noise-reattach always populates at this scale).
- **Naming:** dominant `area`, tie-break `locality_raw` → `cluster_stores` rows must now
  include `area` and `locality_raw` (they currently don't).
- **Real radius:** `haversine_km` from centroid to each member; take the **90th percentile**
  (D16, shrugs off one outlier). Return `radius_km`.
- New return contract: `{label(geographic), center_lat, center_lng, radius_km,
  store_ids, avg_score, avg_price(fact)}`.

**`seed.py` (155-170) + `ml/pipeline.py` `recompute_zones` (55-81)`** — add
`area`/`locality_raw` to row dicts; write `radius_km` + geographic `label`; drop archetype
fields. Extract a shared `_zone_rows(stores)` builder so the two call sites can't drift.

**`ml/chatbot.py` — reconcile against the new contract (required before shipping):**
- Lines 447–467 `zone_exploration`: delete the `"Hidden"`/`"Budget"` branches; rewrite to
  list geographic clusters: `"• {label}: {store_count} stores within ~{radius_km} km,
  avg {avg_score}★"`.
- Lines 350–363 context: `zone` field now carries the geographic name — already soft,
  works once labels change.
- Line 51 intent regex + line 76 sample prompt "Where are the budget thrift zones?":
  **decouple price adjectives from zone intent** — "budget/cheap" routes to the existing
  price filter; "where/which part/neighbourhood" stays `zone_exploration`. Otherwise the
  bot promises a "budget zone" that no longer exists.

**`routers/misc.py` `/api/zones`** — reshape output via `zone_to_dict` (geographic label
+ `radius_km`, drop archetype description). Landing's `stats.zones` count keeps working.

**`routers/clusters.py` (new)** — `GET /api/clusters` (Mode A) reads the same `Zone` rows
via `zone_to_dict`. Register in `main.py`.

**`ml/clusters.py` (new)** — scaffold `discover_clusters(db)`; `find_cluster` /
`split_cluster` land in later phases.

**Frontend (minimal in Phase 1) — `pages/Zones.jsx`:** replace hard-coded `radius: 2200`
(line 34) with `z.radius_km * 1000`; fix the "K-Means…" copy (line 43); labels render as
geographic names. Full rework deferred to Phase 2.

**Migration:** hand-write `ALTER TABLE zones ADD COLUMN radius_km FLOAT;` + backfill by
re-running the pipeline (no Alembic in repo — `LOCATION_SEARCH_PLAN.md` Risk 2). Dev
re-seeds. Record in `DEPLOYMENT.md`.

**Phase-1 verification (`_verify.py`):** geographic naming (every `label` matches a real
member `area`/`locality_raw`; none Budget/Premium/Hidden/Mixed); a cluster contains a
`price_min=NULL`/`review_count=0` store; stored `radius_km` bounds the farthest member;
chatbot `zone_exploration` returns geographic names, not archetypes.

---

## 3. Phase 2 — Interactive Mode B (`/find`) + area & locality centroids
- **`routers/stores.py`** — factor the `nearby` radius loop (68–75) into
  `stores_within(db, lat, lng, radius_km)` so `find_cluster` shares one path.
- **`ml/clusters.py`** — `find_cluster(center, radius_km, min_shops, max_shops)`:
  radius filter → real radius + geographic name → density signal
  (`count<min` → honest-empty; `count>max` → `over_cap=true`). Never truncate.
- **`routers/clusters.py`** — `GET /api/clusters/find?lat&lng&radius_km&min_shops&max_shops`.
- **`routers/stores.py`** — **`GET /api/stores/areas/coords`** →
  `[{name, kind: "area"|"locality", lat, lng, count}]`. Emits **both** `area` centroids
  **and** distinct `locality_raw` centroids (from the stores carrying each locality
  string), so **small sub-localities inside a zone are selectable start points** (Q1 fix).
  Fixes the scope doc's incorrect "areas already coord-backed" claim.
- **Frontend** — `api.js`: `findCluster(params)`, `areaCoords()`. `Zones.jsx`: location
  dropdown (areas + sub-localities) + GPS, radius band+slider+text (D4), min/max controls,
  per-store pins, honest-empty + "widen radius?" CTA, "include solo shops" toggle (D9).
- **Verify:** radius is a hard filter (nothing outside leaks); honest-empty (not padded);
  centroids are true member means; a sub-locality center returns its pocket.

## 4. Phase 3 — Drag + live edit + presets
- **Client clustering util (new)** — in-JS radius filter for live preview while
  dragging/editing (D13); commit calls `/find` for the authoritative result.
- Draggable center; preset buttons (§5.3, pure frontend config, no backend).
- **Verify:** preview↔commit drift is bounded; commit wins.

## 5. Phase 4 — Cap split (D8)
- **`ml/clusters.py`** — `split_cluster()`: recursive HDBSCAN at tighter
  `min_cluster_size`, fallback `KMeans(k=ceil(count/max_shops))` (§13). Reuses the
  `zones.py` primitive.
- Split endpoint; frontend "too many — tap to split" → sub-zone circles.
- **Verify:** sub-zones each ≤ `max_shops`; union = original in-radius set (no shop dropped).

## 6. Phase 5 — Metro overlay + drawn lines (D14)
- **`data/metro_stations_blr.json` (new)** — curated **Purple + Green only**, hand-verified
  snapshot. Store stations **ordered along each line** (array order per line, or add an
  `order` field) so the polyline draws cleanly. Note a review cadence (lines extend).
- **Station pins** toggle + per shop/cluster "~N m from `<station>`" (haversine to nearest).
- **Drawn line polylines (Q2):** render each line as a colored `L.polyline` connecting its
  ordered stations. This is a **visual overlay, not routing** — no A→B path-finding — so it
  stays within D14/D15. "Shops near `<station>`" = station coord as a Mode-B center.
- **Verify:** nearest-station distance is the true haversine min over the asset;
  zero-network across all modes.

---

## 7. Answered design questions
**Q1 — small place inside a zone.** Zones are boundary-free (`center + radius_km`), and
Mode B is coordinate-driven, so geometry always works. The only gap was *resolving a small
place name to coordinates*; the centroids endpoint (Phase 2) now emits `locality_raw`
centroids too, plus GPS fallback — so sub-localities inside a zone are first-class start
points.

**Q2 — drawing metro lines.** Yes, as a static colored overlay (`L.polyline` over
line-ordered stations). Requires the asset ordered per line. Remains overlay-only, not
routing (routing stays chatbot-stage per D15).

---

## 8. Micro-defaults (change anytime)
1. Real-radius statistic: **90th percentile** (D16).
2. `/api/zones` fate: keep as a geographic **alias** of `/api/clusters` through Phase 1–2,
   retire at frontend cutover.
3. Chatbot "budget/cheap zone" queries: **decouple** — route to price filter, not zone intent.

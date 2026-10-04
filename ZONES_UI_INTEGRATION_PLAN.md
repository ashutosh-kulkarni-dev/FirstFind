# Zones UI Integration Plan

Integrate the redesigned Zones UI (`UI's/FirstFind app redesign/FirstFind Zones.dc.html`)
into the live React app, wired to the real backend. The `.dc.html` file is a
DCLogic prototype reading a static `zones-data.js` — we do **not** reuse its
runtime or fake data; we port its **design + interactions** into React and wire
them to the existing API.

## Decisions (locked)

1. **Approach** — Port to React. Rewrite as `pages/Zones.jsx` + a new
   `components/ZonesMap.jsx`, using the live backend and existing CSS tokens.
2. **Nav & chat** — Reuse the app's shared `Navbar` + global `ChatWidget`.
   Recreate the mockup's on-map floating chat bubble, but position it so it
   **never overlaps Leaflet's +/− zoom controls** (zoom bottom-right, chat FAB
   bottom-left, with safe spacing).
3. **Scope** — **Core first, polish after.**
4. **GPS** — Both: real `navigator.geolocation` **and** the area dropdown.

## What already exists (reuse, don't rebuild)

- **Backend endpoints** (all live, richer than the mockup's fake JSON):
  - `GET /api/zones` — precomputed zones + `top_stores` (`misc.py`)
  - `GET /api/clusters` — precomputed zones (Mode A)
  - `GET /api/clusters/find?lat&lng&radius_km` — live radius query (Mode B)
  - `GET /api/clusters/split?lat&lng&radius_km` — sub-zone split
  - `GET /api/metro/stations` — metro lines + stations + per-line color
  - `GET /api/stores` — store list for markers
  - Client wrappers for all of the above already exist in `src/api.js`.
- **CSS design tokens** already in `styles.css` — same palette the mockup uses,
  just renamed. No new token file needed.
- **Leaflet pattern** — `components/MapCanvas.jsx` (Explore) is the reference
  for map init, dark Carto tiles, score-colored `divIcon` markers, popups.
- **Shared chrome** — `Navbar` + global `ChatWidget` already rendered in `App.jsx`.

## Field mapping (mockup → real API)

| Mockup field            | Real API field                          |
|-------------------------|-----------------------------------------|
| `z.clat`, `z.clng`      | `zone.center_lat`, `zone.center_lng`    |
| `z.count`               | `zone.store_count`                      |
| `z.top[].name`          | `zone.top_stores[].name`                |
| `z.avg_price` (₹ x N)   | `zone.avg_price` (rupee number → format)|
| `z.avg_score`           | `zone.avg_score` (may be `null`)        |
| store `score`           | `store.experience_score` (may be `null`)|
| store `priceBand`       | derive from `price_min`/`price_max`     |
| store `cat`             | `store.categories[0]`                   |

Draw-mode cluster card maps to the `find_cluster` result:
`{ label, store_count, avg_score, avg_price, over_cap, honest_empty, stores[] }`.
`over_cap === true` → show the "Split into sub-zones" button (mockup used
`count > 8`; use the backend's `over_cap` instead). `honest_empty` → empty state.

## Architecture — separation of concerns

Goal: no god components, no copy-paste of the Leaflet layer, one home for
shape-mapping, and a clean imperative/declarative boundary. Do **not** port the
mockup's runtime model (single `paint()` re-run on every `componentDidUpdate`) —
that's the spaghetti source. Decompose into layers, each with one job:

**Layer 1 — pure logic (no React, no Leaflet, unit-testable)**
- `lib/zonesView.js` (new) — the single source of truth for API→view mapping and
  formatting. Exports `normalizeZone(zone)`, `normalizeCluster(result)`,
  `priceLabel(...)`, `reachLabel(radiusKm)`, and the `RADIUS_PRESETS` constant
  (`[{label:'Walk',km:1}, …]`). All field mapping from the table above lives here
  and nowhere else.
- `lib/score.js` (exists) — reuse `scoreHex`. Do not re-implement.

**Layer 2 — shared Leaflet glue (reused by Explore + Zones, kills duplication)**
- `lib/map/leaflet.js` (new) — extract `createDarkMap(el)`, `storeMarkerIcon(store,
  selected)`, `storePopupHtml(store)` out of `MapCanvas.jsx`. Refactor
  `MapCanvas.jsx` to consume these so there is exactly one implementation.
- `lib/map/zoneLayers.js` (new) — pure drawing helpers that take a Leaflet
  layerGroup + data and render: `drawZoneCircles`, `drawDrawMode`, `drawMetro`.
  No React, no component state.

**Layer 3 — state orchestration (custom hooks, keep the page thin)**
- `hooks/useZonesData.js` (new) — loads `zones` / `stores` / `metroLines` in
  parallel on mount; exposes `{ zones, stores, metroLines, loading, error }`.
- `hooks/useDrawCluster.js` (new) — given `(center, radiusKm)`, owns the
  debounced `api.findCluster` call and the `api.splitCluster` action; exposes
  `{ result, subZones, loading, split() }`.

**Layer 4 — map component (thin; imperative isolated here)**
- `components/ZonesMap.jsx` (new) — owns the map instance and **one effect per
  concern**, each delegating to a `zoneLayers` helper:
  markers on `stores` change · zone circles on `zones`/`selectedZoneId` · draw
  ring on `center`/`radiusKm` · metro on `metroOn`. Never a single mega-repaint.

**Layer 5 — presentation (small, mostly stateless components)**
- `components/zones/` (new): `ModeToggle`, `DrawControls` (area select + GPS +
  radius slider + presets), `ZoneCard`, `ClusterResult`, `MetroLegend`. These
  mirror the discrete blocks the mockup already renders.

**Layer 6 — page (orchestration only)**
- `pages/Zones.jsx` — wires the two hooks + local UI state (`mode`,
  `selectedZoneId`, `center`, `radiusKm`, `metroOn`, `area`) and composes the
  panel components + `ZonesMap`. No fetching or formatting logic inline.

### Non-negotiable: the Leaflet ⇄ React boundary
React state is the **single source of truth**; Leaflet is a *render target*, never
a second store. This prevents the pin-drag feedback loop (drag → setState →
re-render → re-add pin → jump) the mockup worked around with `_liveRing` /
`_dragCenter`:
- On pin `drag`: update the ring **imperatively** on the Leaflet layer only
  (no `setState`) for smooth live feedback.
- On `dragend` (and map `click`): commit the final center to React state — the
  single point where React learns about the move.
- One directional flow: React state → Leaflet render. Never Leaflet → React
  except at explicit commit events.
- Use `useCallback` for map callbacks so the map isn't re-created; init the map
  once, `map.remove()` on unmount.

## Build plan — Core (Phase 1)

Build **bottom-up**, one layer at a time — each layer is independently testable
before the next depends on it. Every file below has a single responsibility and
no knowledge of layers above it. Nothing imports "sideways" within a layer.

### Step 1 — Layer 1: pure logic (`lib/zonesView.js`)
No React, no Leaflet, no `fetch`. Pure functions + constants only.
- `normalizeZone(zone)` → `{ id, label, clat, clng, radiusKm, count, avgScore,
  avgPrice, topNames[] }` — the *only* place the API→view field mapping lives.
- `normalizeCluster(result)` → `{ label, count, avgScore, avgPrice, overCap,
  empty, stores[] }` from the `find_cluster` shape.
- `normalizeStore(store)` → `{ id, name, area, lat, lng, score, priceBand, cat }`
  (derives `priceBand` from `price_min`/`price_max`, `cat` from `categories[0]`).
- `priceLabel(avgPrice)` / `priceBandLabel(band)` — ₹ formatting in one place.
- `reachLabel(radiusKm)` — the "~15-min walk" copy from the mockup.
- `RADIUS_PRESETS = [{label:'Walk',km:1}, {label:'Scooter',km:3},
  {label:'Auto',km:5}, {label:'Cab',km:8}]`.
- **Test:** trivially unit-testable with sample API payloads; no DOM.

### Step 2 — Layer 2a: shared Leaflet glue (`lib/map/leaflet.js`)
Extract the map primitives currently inlined in `MapCanvas.jsx` so there is one
implementation. No React.
- `createDarkMap(el)` → Leaflet map + Carto dark tiles, `zoomControl` at
  **bottomright**, attribution config. (Lifted from `MapCanvas` init.)
- `storeMarkerIcon(store, selected)` and `storePopupHtml(store)` — the
  score-colored `divIcon` + popup card (uses `scoreHex` from `lib/score.js`).
- **Refactor `MapCanvas.jsx` to import these** — removes the duplicate copy and
  proves the extraction is correct before Zones consumes it.

### Step 3 — Layer 2b: pure draw helpers (`lib/map/zoneLayers.js`)
Each takes `(L, layerGroup, data, opts)` and renders into the group. No React,
no component state — pure "given data, paint this layer."
- `drawStores(L, layer, stores, { onSelect, selectedId })` — markers (reuses
  Layer 2a icon/popup; wires `/store/:id` via a passed handler, not a raw href).
- `drawZoneCircles(L, layer, zones, { selectedId, onSelectZone })` — circle per
  zone (selected solid/filled, others dashed/faint) + count-label `divIcon`.
- `drawDrawMode(L, layer, { center, radiusKm, onDragEnd })` — ring + draggable
  pin. Returns handles so the caller can do the imperative live-drag ring
  update without a rebuild.
- `drawMetro(L, layer, metroLines)` — polyline + station dots per line using the
  API's per-line `color` (the mockup's hardcoded `METRO_COLORS` is dropped).

### Step 4 — Layer 3: state hooks (`hooks/`)
- `useZonesData.js` — parallel `api.zones()` / `api.stores()` / `api.metroStations()`
  on mount; returns `{ zones, stores, metroLines, loading, error }` (already
  normalized via Layer 1). Owns all initial fetching.
- `useDrawCluster.js` — args `(center, radiusKm)`; debounced (~200ms) call to
  `api.findCluster`; returns `{ result, subZones, loading, split, clearSplit }`
  where `split()` calls `api.splitCluster`. Owns all draw-mode fetching + split.
- **These hooks are the only place `api.*` is called** outside the page's trivial
  glue. No component below touches the network.

### Step 5 — Layer 4: map component (`components/ZonesMap.jsx`)
Thin. Owns the map instance; delegates all drawing to Layer 2b. Props:
`mode`, `zones`, `stores`, `metroLines`, `metroOn`, `selectedZoneId`, `center`,
`radiusKm`, `subZones`, `onSelectZone`, `onCommitCenter`.
- **One effect per concern**, never a single mega-repaint:
  - init map once (`createDarkMap`) → cleanup `map.remove()` on unmount.
  - `stores` → `drawStores` into `storeLayer`.
  - `zones` / `selectedZoneId` (zones mode) → `drawZoneCircles` into `zoneLayer`.
  - `center` / `radiusKm` / `subZones` (draw mode) → `drawDrawMode` into `drawLayer`.
  - `metroOn` / `metroLines` → `drawMetro` into `metroLayer`.
- **Leaflet ⇄ React boundary (enforced here):** live pin drag updates the ring
  imperatively (no `setState`); only `dragend`/map-`click` calls `onCommitCenter`.
  Callbacks wrapped in `useCallback`. See the Architecture section's rule.
- `invalidateSize()` on layout changes (used later by Phase 2 fullscreen).

### Step 6 — Layer 5: presentational components (`components/zones/`)
Small, mostly stateless — props in, JSX out, callbacks up. Styled with existing
tokens/classes (reuse `Legend.jsx`, `ScorePill.jsx` where they fit).
- `ModeToggle.jsx` — AI zones / Draw radius segmented control.
- `DrawControls.jsx` — area `<select>` (from `api.areaCoords`), **GPS button**
  (real `navigator.geolocation`, graceful fallback on denial), radius slider
  (0.5–10, step 0.5, `--pct` fill), `reachLabel`, and `RADIUS_PRESETS` buttons.
  Emits `onArea`, `onGps`, `onRadius` — holds no fetching logic.
- `ZoneCard.jsx` — one normalized zone; `onSelect`.
- `ClusterResult.jsx` — normalized cluster (count / avg score / split button when
  `overCap`) + in-range store list; empty state when `empty`.
- `MetroLegend.jsx` — score legend + "Show Namma Metro lines" checkbox.
- `ChatFab.jsx` — on-map floating bubble anchored **bottom-left** (clears the
  bottom-right zoom controls); toggles the **existing global `ChatWidget`** via
  shared state / opens `/chat`. No chat engine of its own.

### Step 7 — Layer 6: page (`pages/Zones.jsx`, replace placeholder)
Orchestration only — wires hooks + UI state + composes components. No `fetch`,
no formatting, no Leaflet.
- Data: `useZonesData()`; draw: `useDrawCluster(center, radiusKm)`.
- UI state: `mode`, `selectedZoneId`, `area`, `center`, `radiusKm`, `metroOn`.
  Defaults `selectedZoneId` = first zone.
- Layout `grid-template-columns: 360px 1fr` (like Explore): left panel composes
  `ModeToggle` + (`DrawControls` in draw mode) + list (`ZoneCard[]` or
  `ClusterResult`) + `MetroLegend`; right side is `ZonesMap` + `ChatFab`.
- Wires callbacks: area/GPS/click/drag-commit → `center`; slider/presets →
  `radiusKm`; card click → `selectedZoneId`.

### Step 8 — Wiring / cleanup
- `App.jsx` route `/zones` already points at `Zones` — no change.
- Ensure `ChatWidget` isn't double-rendered on `/zones`: the `ChatFab` controls
  the same global widget, it does not add a second instance.
- Confirm `MapCanvas.jsx` still works after the Layer 2a extraction (Explore
  regression check).

## Build plan — Polish (Phase 2, after core is verified)

Each item is **additive** and touches one layer only — no rewrites of Phase 1.

- **Fullscreen map mode** — a `fullscreen` UI-state flag in `pages/Zones.jsx`
  toggling a `.fs` layout class (floating glass control panel). Calls
  `ZonesMap.invalidateSize()` after the transition. *No changes to hooks or
  Layer 1–3.*
- **Collapsible side panel** — a `panelCollapsed` UI-state flag + the ‹ › tab
  component (`components/zones/CollapseTab.jsx`), active only in fullscreen.
  Pure presentation; page owns the flag.
- **Per-page dark-mode toggle** — a `components/zones/ThemeToggle.jsx` button
  that toggles the app-wide `html.dark` class and persists to `localStorage`
  (`ff_theme`), matching the mockup. Reuses the app's existing dark support —
  no new tokens, no map/logic changes.

## Verification
- Zones mode: cards match circles; selecting a card flies to + highlights the zone.
- Draw mode: click/drag/slider all recompute the in-range cluster; counts + avg
  score match markers inside the ring; empty state on `honest_empty`.
- Split appears only when `over_cap`; sub-zones cover all in-range stores.
- Metro toggle shows/hides lines with correct per-line colors.
- Chat FAB does not overlap zoom controls at any breakpoint; opens the shared widget.
- Dark mode (app-wide) renders panel + map correctly.

## Open items / assumptions
- **Store markers in Zones mode:** show all stores under the zone circles
  (assumed). If you'd rather show only the selected zone's `top_stores`, say so.
- **Price formatting:** zone `avg_price` is a rupee number; render as `₹<value>`
  (or a ₹/₹₹/₹₹₹ band if you prefer — confirm).
- **Chat FAB target:** toggles the existing global `ChatWidget`. If you want the
  mockup's separate in-map chat panel instead, that's a Phase 2 add.

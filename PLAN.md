# Explore Page — Fix Plan

Four independent fixes. Each is self-contained, touches a minimal set of files, and can
be shipped and tested on its own. No shared state between them, so they can be done in any
order and reverted individually.

| # | Task | Files touched | Type |
|---|------|---------------|------|
| 1 | CARTO tile API key | `lib/map/leaflet.js`, `.env.example` | Config |
| 2 | Metro station name on hover | `lib/map/zoneLayers.js`, `styles.css` | UI fix |
| 3 | Remove category filter | `pages/Explore.jsx` | Removal |
| 4 | Verify store/area search accuracy | new `scripts/verify_search.py` (test only) | Verification |

---

## Task 1 — CARTO tile API key

### Current state
[lib/map/leaflet.js](app/frontend/src/lib/map/leaflet.js#L5) hardcodes the free, keyless
CARTO basemap:

```js
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom: 19 })
```

This endpoint is unauthenticated and rate-limited/deprecated for production use — tiles can
grey out under load. Goal: drive the tile URL + key from build-time env so we can point at a
keyed CARTO account (or any provider) without code changes.

### Change (isolated to one function)
In `createDarkMap`, read config from `import.meta.env` with the current keyless URL as the
default, so **nothing breaks if the key is absent** (local dev keeps working):

```js
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL
  || 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const TILE_KEY = import.meta.env.VITE_MAP_TILE_KEY || ''

const url = TILE_KEY ? `${TILE_URL}${TILE_URL.includes('?') ? '&' : '?'}apikey=${TILE_KEY}` : TILE_URL
L.tileLayer(url, { maxZoom: 19, attribution: '© CARTO © OpenStreetMap' }).addTo(map)
```

### Add to [.env.example](app/frontend/.env.example)
```
# Map tiles. Leave blank to use the free keyless CARTO basemap (dev default).
# For a keyed CARTO account, set the URL template + key from the CARTO dashboard.
VITE_MAP_TILE_URL=
VITE_MAP_TILE_KEY=
```

### Why no spaghetti
Single-function change, env-driven, backward-compatible default. No component or state changes.

### Test
`npm run dev`, confirm map still renders. Set `VITE_MAP_TILE_KEY` in `.env`, restart, confirm
the network tab shows `apikey=` on tile requests.

> **Decision needed from you:** do you already have a CARTO account + key, or should this
> instead switch to a different keyed provider (MapTiler / Stadia)? The wiring above is
> provider-agnostic; only the URL template differs.

---

## Task 2 — Metro station name visible on hover

### Current state
[lib/map/zoneLayers.js `drawMetro`](app/frontend/src/lib/map/zoneLayers.js#L88-L97) already
binds a tooltip:

```js
L.circleMarker([station.lat, station.lng], { radius: 4, ... })
  .bindTooltip(station.name, { direction: 'top', className: '' })
```

Two reasons it feels broken: (a) the 4px dot is a tiny hover target, and (b) `className: ''`
strips the styling hook, so the label is easy to miss on the dark map.

### Change (two small edits, no new deps)
1. In `drawMetro`, make the tooltip reliable and give it a class:
```js
L.circleMarker([station.lat, station.lng], {
  radius: 4, color: '#fff', fillColor: line.color ?? '#888', fillOpacity: 1, weight: 1.5,
})
  .bindTooltip(station.name, { direction: 'top', sticky: true, className: 'metro-tip', opacity: 1 })
  .addTo(layer)
```
`sticky: true` keeps the label pinned to the cursor so a near-miss on the 4px dot still shows it.

2. Add a style block in [styles.css](app/frontend/src/styles.css) so the label reads on dark tiles:
```css
.metro-tip {
  background: #0f1a2b; color: #cfe4f5; border: 1px solid #2a3b52;
  font: 600 11px Inter, sans-serif; padding: 3px 7px; border-radius: 6px; box-shadow: none;
}
.metro-tip::before { border-top-color: #0f1a2b; }  /* tooltip arrow */
```

### Why no spaghetti
No structural change — just tooltip options + one scoped CSS class. Metro layer stays fully
self-contained in `drawMetro`.

### Test
Toggle "Show Namma Metro lines" on, hover a station dot → name appears in a dark chip.

---

## Task 3 — Remove the category filter

### Data justification
Of **131 stores, 127 have empty categories (`[]`)** in [data/stores.csv](data/stores.csv).
The Category dropdown is effectively dead — it filters almost everything to zero. Remove it
from the Explore sidebar.

### Change — frontend only, all in [pages/Explore.jsx](app/frontend/src/pages/Explore.jsx)
Remove exactly these four things:
1. State: delete `const [cats, setCats] = useState([])` (line 27) and
   `const [cat, setCat] = useState('')` (line 34).
2. Fetch: delete `api.categories().then(setCats)...` from the mount effect (line 55).
3. Filter param: delete `if (cat) params.category = cat` (line 79) and remove `cat` from the
   effect dependency array (line 88).
4. UI: delete the entire Category `<label>` block (lines 198–204).

Leave the backend `/api/stores/categories` endpoint and the `category` query param **in place**
— they're harmless, other consumers may use them, and removing them is a separate backend change.

> The `store.cat` **display** in popups/cards stays (it already hides itself via
> `.filter(Boolean)` when empty). This task removes only the *filter control*, not category
> display. Confirm if you also want category text stripped from subtitles.

### Why no spaghetti
Pure deletion of one self-contained filter. `q` and `area` filters are untouched; the store
fetch effect still works with the two remaining params.

### Test
Explore loads, sidebar shows Search + Area + "Open now only" only. Results unaffected.

---

## Task 4 — Verify store & area search accuracy

### Current search logic
[routers/stores.py `list_stores`](app/backend/app/routers/stores.py#L36-L60):
- **`q`** → case-insensitive `ILIKE %q%` across `name`, `area`, `locality_raw`.
- **`area`** → **exact match** `Store.area == area` (dropdown-driven, so exact is fine).

Likely accuracy gaps to check, not assume:
- `q` misses `locality_raw` vs `area` mismatches (e.g. user types "Koramangala 5th Block" but
  `area` is "Koramangala"). ILIKE substring handles the reverse, not this direction.
- No trimming/collapsing of whitespace or accents.
- Exact `area` match fails if the dropdown value and stored value differ in case/spacing.

### Approach — measure before changing (no code change yet)
Add a **read-only** verification script `scripts/verify_search.py` that hits the running API and
reports mismatches. It changes nothing in the app — it's a test harness:

```python
# For each distinct area from /api/stores/areas: call /api/stores?area=<a>,
# assert count > 0 and every returned store's area == a.
# For a sample of store names and localities: call /api/stores?q=<term>,
# assert the intended store appears in results.
# Print a table of: term, expected, found?, count.
```

Run it, read the output, and only then decide which (if any) of the gaps above are real. This
keeps the fix evidence-based instead of speculative.

### Likely follow-up fixes (only if the script shows failures)
- Normalize `q` (strip, collapse spaces) in `list_stores`.
- Add token-based matching (`AND` of `ILIKE %word%` per word) so multi-word queries match.

### Why no spaghetti
Verification is a standalone script under `scripts/`. Any resulting fix is a localized change
to the single `list_stores` query builder.

### Test
`python scripts/verify_search.py` against a running backend → all areas return their own
stores; sampled name/locality queries surface the expected store.

---

## Suggested order
1. **Task 3** (pure deletion, zero risk) — quickest win.
2. **Task 2** (self-contained UI fix).
3. **Task 1** (needs your CARTO key decision).
4. **Task 4** (measure first, then decide on backend fix).

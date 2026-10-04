# Map UX — Implementation Plan (Problems 1–6)

Companion to `map-ux-brainstorm.md`. This is the build plan. Problem 7 (trip planner) is deferred — see `shopping-trip-planner-brainstorm.md`.

**Primary file:** `app/frontend/src/pages/Zones.jsx` (all 6 problems touch it)
**Also:** `app/frontend/src/styles.css`, `data/metro_stations_blr.json`, a new metro-refresh script.

> ⚠️ **Correction to the brainstorm.** The brainstorm's Problem 4 claimed a `setSearchRadius(radius_km)` bug line. **That line does not exist in the actual code.** `commitFind` (Zones.jsx L175-194) never overwrites `radiusKm`. The real bug is a **stale closure** (see Phase 2 below). The fix is different from what the brainstorm sketched.

---

## Build order (dependency-aware)

| Phase | Problem(s) | Why this order |
|-------|-----------|----------------|
| 1 | P1 initial map state + P3 metro styling | Foundational render changes, no state churn |
| 2 | P4 drag radius bug | Isolated logic fix, unblocks confident testing of drag |
| 3 | P5 range slider "Range Card" | Self-contained UI component |
| 4 | P6 fullscreen + side panel | Wraps the controls built in P3/P5 |
| 5 | P2/P3 metro data pipeline | Independent; can run in parallel, lands last |

---

## Phase 1 — Clean initial map + metro stop styling (P1 + P3-styling)

### Goal
On load: show **metro lines + individual store dots only**. No overlapping zone circles. Metro stops render as line-colored rings, not white-bordered dots.

### Changes in `Zones.jsx`

**1a. Stop auto-drawing Mode A zone circles on load.**
- The `useEffect` at L140-154 draws all precomputed `zones` as dashed circles whenever `mode === 'A'`. This is the overlap source.
- Replace with: on load, draw **individual store dots** from `allStores` (already fetched at L101) instead of zone circles.
- Keep the zone *cards grid* below the map (L456-475) — only the on-map circles are removed from the default view.
- Zone circles become opt-in: add a small "Show zone rings" toggle, off by default.

```jsx
// New effect: render individual store dots as the default base layer
const storeDotLayers = useRef([])
useEffect(() => {
  const map = mapObj.current
  if (!map || !allStores.length || mode !== 'A') return
  storeDotLayers.current.forEach(l => l.remove()); storeDotLayers.current = []
  if (showZoneRings) return  // when rings are on, skip dots to reduce clutter
  allStores.forEach(s => {
    if (s.lat == null) return
    const color = s.experience_score >= 4 ? '#6fe3a5'
                : s.experience_score >= 3 ? '#ffc75f'
                : s.experience_score ? '#ff6b6b' : '#9aa69c'
    const dot = L.circleMarker([s.lat, s.lng], {
      radius: 5, color: '#0c0f0d', weight: 1, fillColor: color, fillOpacity: 0.9,
    }).addTo(map).bindPopup(`<b>${s.name}</b><br/>${s.area}`)
    storeDotLayers.current.push(dot)
  })
}, [allStores, mode, showZoneRings])
```
- Add `const [showZoneRings, setShowZoneRings] = useState(false)` and gate the existing L140-154 circle effect on `showZoneRings`.
- Remember to clear `storeDotLayers` in `enterModeB` and `switchToA`.

**1b. Metro stop styling — line-colored ring, transparent fill (P3).**
- Replace `metroIcon` (L67-71):
```jsx
const metroIcon = (color) => L.divIcon({
  className: 'metro-stop',
  html: `<div style="
    width:14px;height:14px;border-radius:50%;
    border:2.5px solid ${color};background:transparent;
    box-shadow:0 0 0 2px rgba(12,15,13,.9);"></div>`,
  iconSize: [14, 14], iconAnchor: [7, 7],
})
```
- Tooltip: include the line name. Pass it through when building pins (L131-135):
  `pin.bindTooltip(`${st.name} — ${line.name}`, {...})`
- Store dots already use a dark border (`#0c0f0d`), so they stay visually distinct from the hollow metro rings.

### Acceptance
- Fresh load shows dots + (if metro toggled on) lines with hollow colored rings. Zero overlapping circles.
- Metro stops are visibly hollow rings in the line color; store dots are solid.

---

## Phase 2 — Fix "size changes when dragging the cluster" (P4)

### Real root cause (corrected)
The draggable marker is created **once** (guard at L219 `if (dragMarker.current) { ...; return }`). Its `drag` and `dragend` handlers are closures created inside `placeDragMarker`, capturing `radiusKm` and `commitFind` **as they were at creation time**. When the user later moves the slider, `radiusKm` state updates and the preview circle grows/shrinks correctly via the L169-172 effect — **but the drag handler still holds the old `radiusKm`.** So on the next drag, `updatePreview(mlat, mlng, radiusKm_OLD)` snaps the circle back to the stale radius → "the size changes when I move it."

Same staleness hits `dragend → commitFind(...)`: it re-queries with the radius captured at marker creation, not the current one.

### Fix — read live values from refs, not from the closure
```jsx
// Add refs that always track the latest values
const radiusRef = useRef(radiusKm)
const includeSoloRef = useRef(includeSolo)
useEffect(() => { radiusRef.current = radiusKm }, [radiusKm])
useEffect(() => { includeSoloRef.current = includeSolo }, [includeSolo])
```
- In the marker `drag` handler: `updatePreview(mlat, mlng, radiusRef.current)`
- In `dragend`: call a ref-reading commit so it uses the current radius.
- `commitFind`: read `radiusRef.current` / `includeSoloRef.current` instead of the closed-over `radiusKm` / `includeSolo`, and drop them from its `useCallback` deps so the marker's bound handler never goes stale.

### Result
- Dragging the pin **pans** the search circle at a **constant** radius.
- Only the slider changes the radius. Exactly the brainstorm's intended behavior — via the correct mechanism.

### Acceptance
- Set radius to 5 km, drag the pin → circle stays 5 km the whole drag.
- Change to 1.2 km, drag again → stays 1.2 km. No snapping.

---

## Phase 3 — "Range Card" slider (P5)

### Goal
Slider becomes the hero control in a dedicated card; presets become secondary pills; add a human-readable label.

### New component `RangeCard` (in `Zones.jsx` or `components/RangeCard.jsx`)
Props: `value`, `onChange` (live, on `input`), `onCommit` (on release), `previewCount`.

```jsx
const modeLabel = (km) =>
  km <= 1.2 ? '~15-min walk'
  : km <= 3 ? '~5-min scooter · 10-min walk'
  : km <= 6 ? '~10-min auto · 15-min cycle'
  : '~15-min cab'
```
- Title: "How far are you willing to go?"
- Full-width custom-styled range input (CSS below), live `{value} km` + `~{previewCount}` readout.
- `modeLabel(value)` line under the slider.
- Preset pills **below** the slider: Walkable 1.2 · Scooter 3 · Auto 6 · Cab 10 (see Open Q on labels).

### CSS (`styles.css`)
```css
.range-card { background:#141a14; border:1px solid #2a3a2a; border-radius:16px; padding:20px 24px; margin-bottom:16px; }
.range-card h3 { font-size:14px; color:var(--text-dim); margin:0 0 16px; font-weight:500; }
.range-track { -webkit-appearance:none; width:100%; height:6px; border-radius:3px;
  background:linear-gradient(to right, var(--accent) 0%, var(--accent) var(--pct), #2a3a2a var(--pct), #2a3a2a 100%);
  outline:none; }
.range-track::-webkit-slider-thumb { -webkit-appearance:none; width:22px; height:22px; border-radius:50%;
  background:var(--accent); cursor:grab; box-shadow:0 0 0 4px rgba(200,240,72,.15); }
.range-track::-moz-range-thumb { width:22px; height:22px; border:none; border-radius:50%; background:var(--accent); cursor:grab; }
.range-presets { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
.range-pill { padding:4px 12px; border-radius:999px; font-size:12px; cursor:pointer;
  background:var(--surface); color:var(--text-dim); border:1px solid var(--border); }
.range-pill.active { background:var(--accent); color:#000; border-color:var(--accent); }
```
- `--pct` set inline: `style={{ '--pct': `${((value-0.5)/(10-0.5))*100}%` }}` — pure CSS fill, no JS repaint.

### Wiring
- Replace the inline preset+slider block (L325-343) with `<RangeCard .../>`.
- `onChange` → `setRadiusKm` (live preview via existing effect). `onCommit` → `handleRadiusCommit`.
- Keep `handleRadiusCommit` unchanged; it now benefits from the Phase-2 ref fix.

### Acceptance
- Slider is the visually dominant control; filled track is lime up to the thumb.
- Label updates live ("~5-min scooter…"). Pills set value + highlight.

---

## Phase 4 — Fullscreen map + sliding side panel (P6)

### Goal
A toggle expands the map to fill the viewport; controls slide in as a docked glass panel; smooth, no jank.

### State + effect (`Zones.jsx`)
```jsx
const [fullscreen, setFullscreen] = useState(false)
const [panelOpen, setPanelOpen] = useState(true)
useEffect(() => {
  document.body.style.overflow = fullscreen ? 'hidden' : ''
  const t = setTimeout(() => mapObj.current?.invalidateSize(), 320) // after CSS transition
  return () => clearTimeout(t)
}, [fullscreen])
useEffect(() => {  // Esc exits
  const h = (e) => { if (e.key === 'Escape' && fullscreen) setFullscreen(false) }
  window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
}, [fullscreen])
```

### Markup
- Wrap the map div in `.map-wrap` that gets `.fullscreen` when active.
- When `fullscreen`, render a `.map-side-panel` (`.collapsed` when `!panelOpen`) containing: area picker, `RangeCard`, metro toggle, include-solo, action buttons — the **same** controls, relocated.
- A corner button toggles fullscreen (⛶ / ✕); a chevron tab toggles `panelOpen`.

### CSS (`styles.css`)
```css
.map-wrap { transition: all .3s ease; }
.map-wrap.fullscreen { position:fixed; inset:0; z-index:900; height:100vh; border-radius:0; margin:0; }
.map-side-panel { position:absolute; top:16px; left:16px; bottom:16px; width:340px; z-index:950;
  background:rgba(20,26,20,.82); backdrop-filter:blur(12px); border:1px solid #2a3a2a;
  border-radius:16px; overflow-y:auto; padding:16px; transition:transform .3s ease; }
.map-side-panel.collapsed { transform:translateX(-360px); }
.map-fs-btn { position:absolute; top:16px; right:16px; z-index:950; }
```

### Gotchas
- **Must** call `map.invalidateSize()` after the transition or tiles render at the old size (grey gaps).
- Lock body scroll while fullscreen.
- The `RangeCard` is one component used in both the normal control row and the fullscreen panel.

### Acceptance
- Click expand → map smoothly fills screen, panel slides in. Tiles fill correctly (no grey).
- Collapse panel → full map visible. Esc / ✕ exits and restores scroll.

---

## Phase 5 — Accurate, auto-updating metro data (P2/P3-data)

### Decision (from brainstorm answer)
Do **not** hit Overpass on client load. Build a scheduled job that queries Overpass, cleans it to a static file, and commit/host that. The `Zones.jsx` renderer is already line-agnostic (loops `metroData.lines`), so only the data file changes.

### Pieces
1. **`scripts/refresh_metro.py`** (or Node) — queries the Overpass API for Namma Metro:
   - Relations tagged `route=subway` / `network="Namma Metro"` in the Bengaluru bbox.
   - Extract per-line: `id`, `name`, `color`, ordered `stations[]` (`name`, `lat`, `lng`, `order`).
   - Add `phase` per station (`operational` | `under_construction`) where derivable from tags.
   - Write to `data/metro_stations_blr.json` in the **existing schema** (drop-in).
2. **GitHub Action** (`.github/workflows/metro-refresh.yml`) — weekly cron: run the script, and if the JSON changed, open a PR / commit. Keeps data fresh as lines open (Yellow Line, etc.) without client rate limits.
3. **Renderer tweak (optional, P3):** if `phase !== 'operational'`, render the polyline segment dashed and the stop ring at reduced opacity, so under-construction lines are visibly distinct.

### Acceptance
- `metro_stations_blr.json` regenerates from Overpass and validates against the current schema.
- Map renders all operational lines (incl. Yellow) with correct colors; the action runs on schedule.

---

## Cross-cutting cleanup
- Any place that removes/creates layers must also handle the new `storeDotLayers`.
- Keep `haversineKm` / `nearestStation` as-is (correct, reused).
- No backend API changes needed for Phases 1–4.

## Test checklist
- [ ] Load: dots + metro only, no overlapping rings
- [ ] Metro stops are hollow line-colored rings, distinct from dots
- [ ] Drag pin at 5 km → radius stays 5 km; change to 1.2 → stays 1.2
- [ ] Range Card: live label, lime fill, pills work, count updates
- [ ] Fullscreen: smooth expand, tiles fill, panel slides, Esc exits, scroll restored
- [ ] Metro JSON regenerates from Overpass and renders all lines

## Open questions (blocking specific phases)
- **P5 preset labels** — transport-mode (Walkable/Scooter/Auto/Cab) vs abstract (Walkable/Neighbourhood/Wide/City)? Plan assumes transport-mode. okay
- **P6 panel dock** — left or right? Plan assumes left. okay
- **P1 metro default** — keep metro toggle off by default, or on (since metro is core)? Plan keeps it a toggle, defaulting off. 
keep metro toggle on by default**
- **P5 preset values** — brainstorm pills say Scooter 3 / Cab 8; current presets use 2/5/10. Confirm final values.
you reason and find the best for this use caase

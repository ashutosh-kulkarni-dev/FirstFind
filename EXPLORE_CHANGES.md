# Explore Page Changes — Implementation Plan

## Files changed
| File | What changes |
|------|-------------|
| `lib/map/zoneLayers.js` | Cluster → lime green; marker size smaller |
| `lib/map/leaflet.js` | Zoom control → bottomleft |
| `lib/zonesView.js` | Presets (diameter-based), reachLabel (time estimates) |
| `components/zones/DrawControls.jsx` | Diameter display, new slider range |
| `components/zones/ChatFab.jsx` | Delete — redundant with global ChatWidget |
| `components/MapExplorer.jsx` | Remove ChatFab import/usage |
| `components/Navbar.jsx` | Add Home link |
| `pages/Explore.jsx` | Remove Legend, always-show DrawControls, fullscreen overlay, default radius |
| `pages/Chat.jsx` | Hero blue header |
| `styles.css` | nav z-index, nav-logo line-through, fullscreen panel |

No new files.

---

## Change 1 — Cluster: lime green

**File:** `lib/map/zoneLayers.js`, function `drawCluster`

Replace both occurrences of `#1478d1` (blue) with `#84cc16` (lime, matches `--score-lime`):
- Ring `color` + `fillColor`: `#1478d1` → `#84cc16`
- Pin div background: `#1478d1` → `#84cc16`

---

## Change 2 — Map markers: smaller

**File:** `lib/map/zoneLayers.js`, function `drawStores`

```js
// Before
const size = selected ? 24 : 18

// After
const size = selected ? 16 : 12
```

Label font stays `9px` — readable at 12px. Ping span uses `size` variable, so it scales automatically.

---

## Change 3 — Zoom + chatbot overlap

**File:** `lib/map/leaflet.js`

```js
// Before
L.control.zoom({ position: 'bottomright' }).addTo(map)

// After
L.control.zoom({ position: 'bottomleft' }).addTo(map)
```

**File:** `components/zones/ChatFab.jsx` — delete this file.
It navigates to `/chat`, which is already covered by the global `ChatWidget` in `App.jsx`. Removing it prevents the bottom-left collision with the newly moved zoom control.

**File:** `components/MapExplorer.jsx`
- Remove `import ChatFab from './zones/ChatFab'`
- Remove `<ChatFab />` from JSX (line 103)

Result: zoom at bottom-left, ChatWidget FAB at bottom-right — no overlap in any mode.

---

## Change 4 — Distance slider: diameter scale + time labels

### 4a. `lib/zonesView.js`

Replace `RADIUS_PRESETS` with diameter-labeled presets (internal `km` is still radius, used by DrawControls state):
```js
export const RADIUS_PRESETS = [
  { label: '600 m', km: 0.3 },   // 600m diameter
  { label: '1.5 km', km: 0.75 }, // 1.5km diameter — walking limit
  { label: '3 km', km: 1.5 },    // 3km diameter — scooter
  { label: '7 km', km: 3.5 },    // 7km diameter — vehicle limit
]
```

Replace `reachLabel` with time-estimate version (walking rate: 600m / 10 min = 60 m/min; scooter ~25 km/h = 417 m/min):
```js
export function reachLabel(radiusKm) {
  const d = radiusKm * 2  // diameter in km
  if (d <= 1.5) {
    const mins = Math.round(d * 1000 / 60)
    return `~${mins} min walk`
  }
  const mins = Math.round(d * 1000 / 417)
  return `~${mins} min · scooter or vehicle`
}
```

### 4b. `components/zones/DrawControls.jsx`

Compute `diameterKm = radius * 2` for all display. Internals still pass `radiusKm` via `onRadius`:

- Displayed value label: `radius * 2 < 1 ? Math.round(radius * 2000) + ' m' : (radius * 2 % 1 === 0 ? (radius * 2) + ' km' : (radius * 2).toFixed(1) + ' km')`
- Slider `min={0.6}` `max={7}` `step={0.3}` `value={radius * 2}`
- `onChange`: `onRadius(parseFloat(e.target.value) / 2)`
- `--pct` fill: `((radius * 2 - 0.6) / 6.4 * 100) + '%'`
- Preset active check: unchanged — `Math.abs(radius - p.km) < 0.01` still correct
- Label above slider: change from "How far will you go?" to "Cluster diameter"

### 4c. `pages/Explore.jsx`

- Change initial `radiusKm` from `2` to `0.3` (default = 600m diameter)

---

## Change 5 — Remove Legend; always-show DrawControls

**File:** `pages/Explore.jsx`

1. Remove `import Legend from '../components/Legend'`
2. Remove the `<Legend />` block (lines 219–221) — the `<DrawControls>` moves here.
3. Restructure the scrollable cluster area:

```jsx
{/* Always-visible distance control — replaces Legend */}
<div style={{ padding: '0 22px 8px', flexShrink: 0 }}>
  <DrawControls radius={radiusKm} onRadius={setRadiusKm} onGps={handleGps} />
</div>

{/* Cluster results — only when center is set */}
<div style={{ flex: 1, padding: '0 22px 12px', overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
  {center ? (
    <>
      <ClusterResult stores={clusterStores} radiusKm={radiusKm} onFocusStore={id => navigate(`/store/${id}`)} />
      <div style={{ display: 'flex', gap: 8 }}>
        {clusterStores.length > 0 && (
          <button onClick={openSavePrompt} ...>+ Save list</button>
        )}
        <button onClick={() => setCenter(null)} ...>Clear</button>
      </div>
    </>
  ) : (
    <div style={{ ... }}>
      Double-click anywhere on the map to cluster stores within this radius.
    </div>
  )}
</div>
```

DrawControls is now always visible regardless of cluster state. The hint text updates to reference "this radius" since the slider is now visible.

---

## Change 6 — Map covers banner

**File:** `styles.css`

```css
/* Before */
.nav { ...; z-index: 50; }

/* After */
.nav { ...; z-index: 200; }
```

This ensures the sticky nav sits above Leaflet's internal overlay panes (which can reach z-index ~600 but within their own stacking context — bumping the nav ensures it wins any stacking context conflicts).

---

## Change 7 — Fullscreen: slider overlay panel

**File:** `pages/Explore.jsx`

When `mapFull` is true, render a compact fixed panel on the right side of the map containing only `DrawControls`:

```jsx
{mapFull && (
  <div className="explore-full-panel">
    <DrawControls radius={radiusKm} onRadius={setRadiusKm} onGps={handleGps} />
  </div>
)}
```

**File:** `styles.css`

```css
.explore-full-panel {
  position: fixed; top: 70px; right: 16px; z-index: 400;
  width: 260px; background: var(--surface); border: 1px solid var(--line);
  border-radius: 14px; padding: 14px; box-shadow: var(--shadow-md);
}
```

Panel sits below the fullscreen toggle button (top: 70px ≈ nav height 60px + gap), above map layers (z-index 400 < zoom's Leaflet stack but above map tiles), to the right — does not obscure the map much.

---

## Change 8 — Navbar: add Home + FIRSTFIND line-through

**File:** `components/Navbar.jsx`

```js
// Before
const LINKS = [
  { to: '/explore', label: 'Explore' },
  { to: '/chat', label: 'Assistant' },
]

// After
const LINKS = [
  { to: '/', label: 'Home' },
  { to: '/explore', label: 'Explore' },
  { to: '/chat', label: 'Assistant' },
]
```

**File:** `styles.css`

```css
/* Before */
.nav-logo { color: #fff; font-family: var(--font-display); font-size: 23px; letter-spacing: -.5px; }

/* After */
.nav-logo { color: #fff; font-family: var(--font-display); font-size: 23px; letter-spacing: -.5px; text-decoration: line-through; }
```

---

## Change 9 — Chat page: hero blue header

**File:** `pages/Chat.jsx`

The `.chat-head` div currently uses `var(--ink)` text on a white background. Change to the landing hero blue gradient with white text — same gradient as the "Our Features" section:

```jsx
// Before
<div className="chat-head">
  <div className="anton" style={{ fontSize: 26, color: 'var(--ink)' }}>STYLE ASSISTANT</div>
  <p className="muted" style={{ fontSize: 13, marginTop: 2 }}>...</p>
</div>

// After: add background to the outer wrapper
<div className="chat-head" style={{ background: 'linear-gradient(145deg, #0587ca, #0088c7 65%, #0879bd)', borderRadius: '0 0 16px 16px', padding: '20px 24px 18px' }}>
  <div className="anton" style={{ fontSize: 26, color: '#fff' }}>STYLE ASSISTANT</div>
  <p style={{ fontSize: 13, marginTop: 2, color: 'rgba(255,255,255,.82)' }}>...</p>
</div>
```

**File:** `styles.css`

`.chat-head` currently has `padding: 20px 24px 6px`. The inline style overrides will handle the padded blue header cleanly without touching the CSS class (avoids cascade side-effects on other elements using the same class).

---

## Implementation order

1. `zoneLayers.js` — cluster green + marker size (isolated)
2. `leaflet.js` + `MapExplorer.jsx` + delete `ChatFab.jsx` — zoom + fab cleanup
3. `zonesView.js` — presets + reach label
4. `DrawControls.jsx` — diameter display
5. `Explore.jsx` — Legend removal, DrawControls always-on, fullscreen overlay, default radius change
6. `styles.css` — nav z-index, nav-logo line-through, fullscreen panel class
7. `Navbar.jsx` — Home link
8. `Chat.jsx` — blue header

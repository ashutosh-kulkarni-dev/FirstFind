# Map UX Brainstorm — ThriftFind

## Current State (Problems to Solve)

| # | Problem | Location in Code |
|---|---------|-----------------|
| 1 | Pre-search clusters overlap and are confusing | `Zones.jsx` — precomputed zone circles, `Explore.jsx` — store markers |
| 2 | Metro stops show as plain dots, hard to distinguish from store pins | `Zones.jsx` L288-305 — `divIcon` 10px circles |
| 3 | Metro line data may be outdated (only Purple + Green, no Yellow/Pink/etc.) | `data/metro_stations_blr.json` |
| 4 | Dragging the cluster manually changes its size (annoying) | `Zones.jsx` — draggable marker + live radius recalculation |
| 5 | Cluster radius slider UX is poor — slider is buried, presets unclear | `Zones.jsx` L325-342 |
| 6 | No fullscreen map; controls stacked above/below instead of on the side | `Zones.jsx` — 400px map box + control row |
| 7 | Cluster shop list is read-only — no select/save/plan for a shopping trip | `Zones.jsx` — flat card list; `saveStore` + `Interaction` exist but no lists |

---

## Problem 1 — Initial Map State (Before Search)

### What happens now
- `Zones.jsx` Mode A renders precomputed zone circles (2.2 km dashed rings) at centroids, overlapping heavily in dense areas like BTM/Koramangala/Indiranagar
- Multiple overlapping rings at the same zoom level is visually noisy
- User has no obvious entry point

### Goal
> The map initially shows only metro lines + store dots (individual shops). No cluster bubbles at all until the user actively invokes clustering.

### Options

**A. Lazy clusters (recommended)**
- On page load: render metro polylines + individual store markers only
- Cluster circles appear only after: (a) user drops a pin, or (b) user picks a preset zone from a list
- This matches the mental model: "show me the map, I'll decide where to zoom in"
- Store dots can be color-coded by score (green/amber/red) just like Explore page

**B. Heatmap fallback**
- Instead of circles, render a subtle density heatmap using Leaflet.heat
- Shows "hot zones" without hard boundaries
- Pro: no overlapping rings. Con: adds a dependency, harder to interact with

**C. Zoom-gated clusters**
- Show only individual stores at zoom ≤ 12, auto-cluster at zoom ≥ 13 using Leaflet.markercluster
- Familiar to users from Google Maps / Airbnb
- Pro: scales naturally. Con: Leaflet.markercluster is heavy and changes the interaction model significantly

Answer: Option A


### Decision
Go with **Option A**. Keep the initial map clean. Zone circles only appear on demand. Store dots always visible.

### Implementation sketch
```jsx
// On mount: fetch all stores, render as simple CircleMarkers (no cluster rings)
// metroLayer always visible
// zoneLayer starts empty, populated only when user triggers a search
const [showZones, setShowZones] = useState(false);
```

---

## Problem 2 — Metro Stop Styling

### What happens now
- Each station is a `divIcon` with a 10px circle, white border, colored background
- At city zoom (12), they're tiny and visually identical to store pins
- The dots are ugly and blend in

### Goal
> Metro stops should look unmistakably like metro stops — use the line color prominently, no confusion with store dots.

### Options

**A. Colored ring + no fill (recommended)**
- Circle outline = line color (purple / green / yellow)
- Interior = transparent or very dark (matches map background)
- No dot fill → visually distinct from solid store markers
- Larger than store markers (14-16px vs 9px for stores)
- On hover: tooltip with station name

**B. Pill / badge shape**
- Elongated pill, line color background, white station initial
- Pro: clear metro branding. Con: cluttered at city zoom

**C. Mini line-colored squares**
- Simple 8x8px squares, line color fill
- Easy to implement. Meh visually.

**D. Station icon from BMRCL branding**
- SVG of the "m" metro logo per line
- Most authentic. Complex to implement, SVG per line.

Answer: Option A

### Decision
**Option A** — colored ring, transparent fill. Clean, scalable, zero clutter.

```css
/* Purple line stop */
border: 2.5px solid #7B2D8B;
background: transparent;
border-radius: 50%;
width: 14px; height: 14px;

/* Green line stop */
border: 2.5px solid #007A3D;
```

- Remove the white `border` currently on store pins to keep them distinct
- Add line label to tooltip: "Indiranagar — Purple Line"

---

## Problem 3 — Metro Data Accuracy

### Current state
- `metro_stations_blr.json` has Purple Line (44 stations) and Green Line (38 stations)
- Marked as "Phase 1 + 2A/2B", reviewed 2024-12
- Namma Metro has since opened Yellow Line (RV Road ↔ Bommasandra, partial) and has Pink/Blue lines planned

### Plan
- User will provide a corrected metro map
- New JSON should follow the same schema:
  ```json
  { "id": "yellow", "name": "Yellow Line", "color": "#FFD700", "stations": [...] }
  ```
- The renderer in `Zones.jsx` is already line-agnostic (loops over `data.lines[]`), so new lines work automatically once the JSON is updated
- Consider adding a `"phase"` field per station (`"operational"` | `"under_construction"` | `"planned"`) to render non-operational stations differently (dashed line, grayed stop ring)

Answer :
 Choose the easiest one out of the below to implement:
 1. The Dynamic Choice: Live OpenStreetMap Overpass API
 2. The Official Path: BMRCL Static GTFS via IUDX
 3. Open-Source Boilerplates & Repositories

 I want the metro map to be accurate, and update when new lines become operational.
 For a production application, do not query public Overpass endpoints on every single client page load, as your clients could encounter strict API rate limits.Instead, construct a daily or weekly internal cron job (e.g., via GitHub Actions) to run the Overpass API query, clean up the output into a single static GeoJSON file, and host that file on your own server or CDN endpoint

---

## Problem 4 — Dragging Changes Cluster Size

### What happens now
- When user drags the center marker, `updatePreview()` recalculates radius using haversine to nearest store cluster
- This mutates the radius state mid-drag, causing the circle to resize as the pin moves
- Disorienting: moving the center changes the "how far you can walk" radius, which should be user-controlled, not position-dependent

### Root cause
`handleRadiusCommit()` calls the backend which re-clusters based on actual store distribution in the new location, and the returned `radius_km` from the backend replaces the user's chosen radius.

### Goal
> Moving the pin should pan the search area. The radius circle should move with the pin but NOT resize. Only the user can resize.

### Options

**A. Lock radius during drag (recommended)**
- Store `lockedRadius` = user's last explicitly set radius
- During drag, only update marker position + circle center; never touch radius
- On drag end, hit backend with `lockedRadius` (not backend-returned radius)
- Recompute store list, but don't update the radius state from the backend response

**B. Snap radius to nearest preset on drag end**
- After drag, snap the returned radius to the nearest preset (1.2, 2, 5, 10 km)
- Less jarring. Still changes the radius from what the user set.

**C. Two distinct modes: "pan" vs "resize"**
- Pin drag = pan only
- Separate dedicated resize handle (drag the circle edge)
- Most powerful. Most complex to implement.   

Answer: Option A

### Decision
**Option A** is the right fix — minimal code change, correct behavior.

```jsx
// Current (broken): radius comes from backend after drag
const { stores, radius_km } = await api.findCluster(lat, lng, searchRadius);
setSearchRadius(radius_km); // ← this is the bug line

// Fixed: keep user's radius, only update store list
const { stores } = await api.findCluster(lat, lng, searchRadius);
// don't touch searchRadius state
```

---

## Problem 5 — Cluster Radius Slider UX

### What happens now
- Slider is a small HTML range input buried in a controls row with area dropdown + metro toggle + action buttons
- 4 preset buttons above the slider in a flex row
- No visual affordance that the slider is the primary control
- No explanation of what the radius means in human terms ("that's about a 15-min walk")
- Range: 0.5–10 km, step 0.5 km

### Goal
> The slider must be the hero control. User sees it first, intuitively understands radius = "how far you'll go". Presets are secondary helpers, not the primary UI.

### Proposed Design — "Range Card"

```
┌──────────────────────────────────────────────────────┐
│  How far are you willing to go?                      │
│                                                       │
│  [●━━━━━━━━━━━━━━━━━━━━━━━━━━━━○] 2.0 km             │
│                                                       │
│  ~ 25-min walk  ·  5-min scooter                     │
│                                                       │
│  Quick picks:  [Walkable 1.2]  [Scooter 3]  [Cab 8]  │
└──────────────────────────────────────────────────────┘
```

### Design details

**Slider itself**
- Full-width inside the card (not squished next to 4 other controls)
- Thick track (6-8px), rounded caps
- Thumb: larger circle (20px), accent lime color (`--accent: #c8f048`)
- Custom CSS — no browser default styling
- Live distance readout next to the thumb (updates on every `input` event, not just `mouseup`)

**Human-readable annotation**
- Below the slider: auto-generated label based on radius:
  - ≤ 1.2 km → "~15-min walk"
  - 1.3–3 km → "~5-min scooter / 10-min walk"
  - 3–6 km → "~10-min auto / 15-min cycle"
  - 6–10 km → "~15-min cab"
- This answers "what does 2 km mean for me?" without the user having to think

**Preset pills (secondary)**
- Small pill buttons below the annotation, not above the slider
- 3-4 pills max: Walkable · Scooter · Auto · Cab
- Clicking a preset sets the slider AND shows the label — no separate state
- Visually smaller than the slider (secondary role)

**The slider should live in a dedicated floating card or sidebar section**, not inline in a cramped control row.

### CSS sketch
```css
.range-card {
  background: #141a14;
  border: 1px solid #2a3a2a;
  border-radius: 16px;
  padding: 20px 24px;
  margin-bottom: 16px;
}

.range-card h3 {
  font-size: 14px;
  color: var(--muted);
  margin-bottom: 16px;
  font-weight: 500;
}

.range-track {
  -webkit-appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: linear-gradient(
    to right,
    var(--accent) 0%,
    var(--accent) var(--pct),
    #2a3a2a var(--pct),
    #2a3a2a 100%
  );
  outline: none;
}

.range-track::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 22px; height: 22px;
  border-radius: 50%;
  background: var(--accent);
  cursor: grab;
  box-shadow: 0 0 0 4px rgba(200, 240, 72, 0.15);
}
```

The gradient trick (`var(--pct)`) makes the filled portion lime and unfilled portion dark — no JS needed for the fill effect.

---

## Problem 6 — Fullscreen Map with Side Controls

### What happens now
- `Zones.jsx` map is a fixed 400px-height box inside a max-1200px container
- Controls sit in a row *above* the map; the store cards sit *below* it
- To adjust radius or read the shop list, the user scrolls away from the map — the map and its controls never share the screen comfortably
- On a laptop the actual map viewport is tiny relative to the browser window

### Goal
> A button that smoothly expands the map to fill the screen, with all the editing controls (radius slider, area picker, metro toggle) sliding in as an overlay panel on the side — not stacked above/below. Easy, smooth, no layout jank.

### Options

**A. CSS-driven fullscreen overlay (recommended)**
- Map container gets a `.fullscreen` class that animates it to `position: fixed; inset: 0; z-index: 900`
- Controls move into a floating glass panel docked left (or right), `position: absolute` over the map
- Leaflet needs `map.invalidateSize()` called after the CSS transition ends (`transitionend` listener) so tiles re-render to the new dimensions
- Pros: no new dependency, uses existing dark/glass design language, transitions are smooth (`transition: all .3s ease`)
- Cons: must remember `invalidateSize()`, and lock body scroll while fullscreen (`overflow: hidden` on `<body>`)

**B. Native Fullscreen API (`element.requestFullscreen()`)**
- True OS-level fullscreen (hides browser chrome too)
- Pros: maximal screen real estate, one API call
- Cons: browser-styled exit prompts, harder to overlay React controls reliably across browsers, feels heavy for "just make the map bigger". Escape-key handling and cross-browser prefixes add friction.

**C. Leaflet fullscreen plugin (`leaflet.fullscreen`)**
- Drop-in control button on the map
- Cons: another dependency, and the control panel would still be Leaflet-native, not our React side panel — doesn't satisfy "options come in on the side"

### Decision
**Option A** — CSS-driven fullscreen with a sliding side panel. Keeps our design system, keeps the React controls, smooth to animate.

### Layout sketch
```
Normal:                          Fullscreen (Option A):
┌─────────────────────┐          ┌────────────────────────────────┐
│  controls row        │          │ ┌─────────┐                    │
├─────────────────────┤          │ │ Range    │                    │
│                      │          │ │ slider   │      MAP           │
│      MAP (400px)     │          │ │ Area ▾   │   (full screen)    │
│                      │          │ │ Metro ☑  │                    │
├─────────────────────┤          │ │ [shops]  │              [⛶ x] │
│  shop cards below    │          │ └─────────┘                    │
└─────────────────────┘          └────────────────────────────────┘
   side panel (glass, docked left, scrollable, collapsible)
```

### Implementation notes
```jsx
const [fullscreen, setFullscreen] = useState(false);

useEffect(() => {
  if (!mapRef.current) return;
  // wait for the CSS transition to finish, then let Leaflet recompute
  const t = setTimeout(() => mapRef.current.invalidateSize(), 320);
  document.body.style.overflow = fullscreen ? 'hidden' : '';
  return () => clearTimeout(t);
}, [fullscreen]);
```
```css
.map-wrap { transition: all .3s ease; }
.map-wrap.fullscreen {
  position: fixed; inset: 0; z-index: 900;
  border-radius: 0; height: 100vh;
}
.map-side-panel {
  position: absolute; top: 16px; left: 16px; bottom: 16px;
  width: 340px; z-index: 950;
  background: rgba(20,26,20,.82); backdrop-filter: blur(12px);
  border: 1px solid #2a3a2a; border-radius: 16px;
  overflow-y: auto; transition: transform .3s ease;
}
.map-side-panel.collapsed { transform: translateX(-360px); }
```
- Add a small toggle (⛶ / ✕) at a fixed map corner for enter/exit
- The side panel should be collapsible (a chevron tab) so the user can see the whole map when they want, then slide controls back in
- Escape key exits fullscreen
- The "Range Card" from Problem 5 lives *inside* this side panel when fullscreen — one component, two placements

> **Note:** Problem 7 (shopping list / trip planner) has been split out to `shopping-trip-planner-brainstorm.md` — deferred for a later pass.

---

## Summary — What to Build

| Priority | Problem | Fix |
|----------|---------|-----|
| P0 | Overlapping initial clusters | Load only store dots + metro on init; zone circles on demand |
| P0 | Radius changes on drag | Lock radius during drag; don't apply backend-returned radius |
| P1 | Metro stop styling | Colored ring, transparent fill, sized 14-16px |
| P1 | Slider UX | Dedicated "Range Card" — slider as hero, presets as pills, human labels |
| P1 | Fullscreen map + side controls | CSS-driven fullscreen overlay, sliding glass side panel, `invalidateSize()` after transition |
| P2 | Metro data | Overpass API via weekly cron → static GeoJSON on CDN; render lines/stops from that |

> Shopping list / trip planner (was Problem 7) is deferred — see `shopping-trip-planner-brainstorm.md`.

---

## Open Questions

1. **Yellow Line stations** — user will provide the updated metro JSON. What format? Same as current `metro_stations_blr.json`.
2. **Presets** — "Walkable / Scooter / Auto / Cab" vs "Walkable / Neighbourhood / Wide / City"? Transport-mode framing (walkable/scooter) feels more intuitive for Bengaluru.
3. **Store dots on initial load** — should they be clustered using Leaflet.markercluster at city zoom (many stores = overlapping dots too), or just rendered all at once? Probably fine for now since the dataset is small (<100 stores).
4. **Metro toggle** — keep it as a checkbox, or make it always-on by default since metro context is central to the ThriftFind premise?
5. **Side panel dock** — left or right side when fullscreen? Left keeps controls near the natural reading start; right keeps the map's Bengaluru-east (Whitefield/Indiranagar) stores unobscured.

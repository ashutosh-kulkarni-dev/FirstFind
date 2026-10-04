# FIRSTFIND — UI Rebuild Plan

**Date:** 2026-08-19
**Decision basis:** Full rebrand ThriftFind → **FIRSTFIND**. The current React frontend is
**discarded entirely** (archived for retrieval, not reused). The new frontend is rebuilt
**using the `UI's` folder as the sole visual reference**, wired to the **existing, untouched
backend**.

---

## 1. Scope & ground rules

- **Backend is frozen.** No route, model, or ML change. `app/backend/**` is untouched. The
  only exception is the two *small, additive* features in §6 (anomaly flag) — and even those
  have a frontend-only fallback so the backend need not change.
- **`app/frontend/src/api.js` is the contract and is kept verbatim.** It already exposes every
  endpoint the mockups imply. It is the one file that survives the discard.
- **The mockups are references, not code.** They use a throwaway `x-dc` / `DCLogic` framework
  with fake in-file data. We reimplement their *layout, palette, typography, and
  micro-interactions* in real React against the real API. We do **not** import their JS.
- **The old UI is archived, not deleted.** Move current components/pages/styles into
  `app/frontend/_archive_ui_v1/` before writing new ones, so nothing is lost.

---

## 2. Source mockups (what we mine from each)

All under `UI's/App animation and interactivity integration/`:

| File | Reference for | Real page it becomes |
|------|---------------|----------------------|
| `FirstFind Landing.dc.html` | Hero collage, nav, "Discover" + "Trust & Stats" sections, animated dark-mode toggle, count-up stat | `pages/Landing.jsx` |
| `FirstFind Explore.dc.html` | Split filter-sidebar + full map, AI-score legend, marker popup, "selected store" panel | `pages/Explore.jsx` |
| `FirstFind Chat.dc.html` | Centered thread, suggestion chips, intent tags, inline store cards, "view on map" card, typing dots | `pages/Chat.jsx` + `ChatCore.jsx` |
| `FirstFind Store.dc.html` | AI-score ring, sentiment bar, review list + **anomaly flag**, star composer w/ **live sentiment**, "shoppers also liked" | `pages/StoreDetail.jsx` |
| `FirstFind Zones.dc.html` | AI-zones ⟷ Draw-radius toggle, radius slider + **transport presets**, zone cards | `pages/Zones.jsx` |

No mockup exists for **Auth** or the floating **ChatWidget** — both are rebuilt in the new
palette using the mockups' component idioms (nav, buttons, inputs) for consistency.

---

## 3. Design system (extracted from mockups)

Rewrite `styles.css` from scratch around these tokens.

### Palette (light default)
```
--surface:      #ffffff      /* cards, panels */
--bg:           #eef2f4      /* app background */
--nav:          #0f1a2b      /* dark navy nav bar */
--ink:          #050505 / #0f1a2b   /* headings */
--muted:        #6c7885      /* secondary text */
--line:         #dde3e8      /* borders */
--brand-blue:   #1478d1      /* primary / links */
--brand-blue-2: #33a0e6      /* focus, active underline, accents */
--brand-pink:   #ff2865      /* landing hero highlight only */
--map-bg:       #141d2b      /* map canvas */
```

### AI-score color scale (used on markers, pills, rings — consistent everywhere)
```
>= 4.5  #22c55e  Exceptional
>= 4.0  #84cc16  Great
>= 3.5  #f59e0b  Good
<  3.5  #f43f5e  Below
none    #94a3b8  Unrated
```

### Sentiment colors
```
positive #16a34a   neutral #64748b   negative #e11d48   flagged/anomaly #d97706
```

### Typography
- **Display:** `Anton` (headings, logo, big numbers) — Google Fonts.
- **Body:** `Inter` 400–800 — Google Fonts.
- Add both to `index.html` `<head>` (mockups use `fonts.googleapis.com`).

### Dark mode
Landing mockup has an animated circle-reveal toggle. Implement as a `<html class="dark">`
switch with a `--surface`/`--bg`/`--nav` remap. Dark mode shifts **blue areas to near-black;
white surfaces stay white** (per mockup's `applyTheme`). Persist choice in `localStorage`.

### Shared keyframes (from mockups)
`fadeUp`, `pop`, `ping` (open-marker pulse), `ring` (zone circle grow), `typingDot`.
Collect into `styles.css` so every page reuses them.

---

## 4. Component inventory (new `src/` tree)

```
src/
  main.jsx            keep (router root)
  App.jsx             rebuild: routes + <Navbar> + <ChatWidget> (hidden on /chat, /auth)
  api.js              KEEP VERBATIM
  theme.js            NEW: dark-mode context + localStorage
  styles.css          rewrite from tokens above
  components/
    Navbar.jsx        dark navy bar, Anton logo "FIRSTFIND", underline-active links,
                      greeting/logout, dark-mode toggle
    StoreCard.jsx     white card, Anton name, score pill, area·category, open/price
    ScoreRing.jsx     NEW: circular SVG AI-score gauge (Store header)
    ScorePill.jsx     NEW: small colored rating chip (reused across pages)
    MapCanvas.jsx     Leaflet wrapper (real map — see §5) styled to --map-bg
    MiniMap.jsx       read-only Leaflet embed for chat bubbles
    ChatCore.jsx      thread + chips + input, renders bot payload (stores/map/action/intent)
    ChatWidget.jsx    floating FAB + dock (ChatCore compact)
    Legend.jsx        NEW: AI-score legend block (Explore sidebar)
  pages/
    Landing.jsx  Explore.jsx  StoreDetail.jsx  Chat.jsx  Zones.jsx  Auth.jsx
```

---

## 5. Map decision (important)

The mockups fake the map with a static SVG grid. **We do NOT copy that.** The existing app
already uses **Leaflet** with real store coordinates — objectively better than the mockup.

**Plan:** Rebuild `MapCanvas.jsx` on Leaflet but style it to *look like the mockup*:
dark `--map-bg` tiles, circular rating markers colored by score, open-store "ping" pulse,
and the mockup's white popup card (name / area·cat / score pill / open badge / "View store →").
This gives the mockup's aesthetic on top of a real, pannable map. Same approach for the Zones
map overlay (real geometry, mockup styling for zone rings + radius circle + transport pins).

---

## 6. Per-page specs

### 6.1 Landing (`pages/Landing.jsx`)
- **Nav** (shared component): logo, HOME / EXPLORE / ASSISTANT / ZONES, `SAVED (n)`,
  dark-mode toggle, `OPEN APP` → `/explore`.
- **Hero:** Per your instruction, follow the mockup — **flat collage hero** (Anton
  "FIRSTFIND" wordmark with per-letter hover, tagline, EXPLORE STORES CTA, image collage,
  VINTAGE/STREET/DESIGNER/RETRO ticker). *Hero3D / Three.js is discarded with the old UI.*
- **Discover section:** "DISCOVER THRIFT STORES THAT DEFINE YOUR STYLE" + tilt-on-hover
  glass rating card.
- **Trust & Stats:** 3-up cards; middle card is an animated **count-up** ("first-visit match
  rate"). Wire real numbers where available (`api.stores()` count, `api.areas()`,
  `api.zones()`); keep mockup copy for the rest.
- **Interactions to port:** per-letter wordmark hover, count-up on mount, `SAVED` pulse,
  3D-tilt card, circle-reveal dark-mode toggle.

### 6.2 Explore (`pages/Explore.jsx`)
- Layout: dark nav + `332px` sidebar + full map (mockup grid).
- **Sidebar:** Anton "EXPLORE STORES" title, Search input, Area `<select>`, Category
  `<select>`, "Open now only" checkbox, `{count} RESULTS` + Reset, **AI-score legend**
  (`Legend.jsx`), and a "Selected store" panel that fills when a marker is clicked.
- **Data:** `api.areas()`, `api.categories()`, `api.stores(filters)` on every filter change
  (already how the API works). Populate selects from real areas/categories, not the mockup's
  hardcoded list.
- **Map:** real Leaflet (`MapCanvas`), markers colored by `experience_score`, open pulse,
  popup → `/store/:id`.

### 6.3 Store detail (`pages/StoreDetail.jsx`)
- **Header card:** Anton store name, OPEN/CLOSED badge, category chips, description, meta grid
  (hours / price range / phone / instagram), **ScoreRing** (circular AI-score gauge), Save
  button (`api.saveStore`, auth-gated).
- **Reviews column:** sentiment bar (positive/neutral/negative %), review list with per-review
  sentiment badge, **anomaly flag** for suspicious reviews (see below), then a composer:
  star picker + textarea + **live sentiment preview** ("Live sentiment: Positive") + Post
  (`api.addReview`, then refetch at 3s/7s for async HF scoring — existing behavior).
- **Sidebar:** "SHOPPERS ALSO LIKED" from `similar[]` in `api.store(id)`, with `% match`.
- **Anomaly flag (feature §):** mockup flags spammy reviews (excessive `!`, ALL-CAPS) as
  "possibly fake". Backend has no such field today. **Do it frontend-only** with the mockup's
  heuristic (`>=3 exclamation marks` or `>60% caps`) → amber badge + tinted card. No backend
  change required. (If later promoted to a real model, add a `flagged` field server-side.)
- **Live sentiment preview (feature §):** frontend-only, reuse the mockup's keyword heuristic
  purely for the *composer preview*; the authoritative score still comes from the backend on
  submit.

### 6.4 Chat (`pages/Chat.jsx` + `ChatCore.jsx`)
- Centered `720px` column: "STYLE ASSISTANT" header, scrolling thread, suggestion chips,
  rounded input with ↑ send.
- **Wire to real backend** (`api.chat`) — not the mockup's fake router. Render the real bot
  payload: `text`, `intent` (as a small tag), `stores[]` (inline `StoreCard` grid),
  `map` (→ `MiniMap`), `action` (→ "View on full map" button deep-linking `/zones?lat=&lng=&radius=`),
  `suggestions[]` (→ chips). Typing-dots indicator while awaiting response.
- Same `ChatCore` powers the floating `ChatWidget` in compact mode.

### 6.5 Zones (`pages/Zones.jsx`)
- Dark nav + `352px` control panel + full map.
- **Mode toggle:** "AI zones" (precomputed, `api.zones()`/`api.clusters()`) vs "Draw radius"
  (interactive).
- **Draw mode:** Center-area `<select>` (from `api.areaCoords()`), radius slider, **transport
  preset buttons** (Walk / Scooter / Auto / Cab → set km), click-map-to-set-center. Query with
  `api.findCluster()`; offer "Split into sub-zones" (`api.splitCluster()`) when over cap.
- **AI-zones mode:** zone cards (label, score pill, store count, radius, price, top stores) +
  zone rings drawn on the real map.
- **Keep existing advanced behavior** the old UI already had and the mockup lacks: metro
  overlay (`api.metroStations`/`metroNearest`), deep-link `?lat=&lng=&radius=` entry from chat,
  fullscreen map. These are re-implemented, styled to the mockup — not dropped.

### 6.6 Auth (`pages/Auth.jsx`) — no mockup
- Rebuild login/register in the new palette using mockup input/button idioms. Same flow:
  `api.register` / `api.login` → `setAuth` → redirect home.

---

## 7. Feature deltas vs. old UI

| Item | Old UI | Mockup | Plan |
|------|--------|--------|------|
| Theme | dark only | light + animated dark toggle | **Add** light default + dark toggle |
| Brand | ThriftFind | FIRSTFIND | **Rebrand** everywhere (logo, titles, copy, favicon) |
| Display font | Space Grotesk | Anton | **Switch** |
| Hero | Three.js 3D | 2D collage | **Replace** with collage (3D discarded) |
| AI-score ring | — | circular gauge | **Add** `ScoreRing` |
| Review anomaly flag | — | "possibly fake" badge | **Add** (frontend heuristic) |
| Live sentiment preview | — | in composer | **Add** (frontend heuristic) |
| Transport radius presets | slider only | Walk/Scooter/Auto/Cab | **Add** preset buttons |
| Real Leaflet map | ✅ | fake SVG | **Keep Leaflet**, style like mockup |
| Metro overlay / deep-links / fullscreen | ✅ | — | **Keep** (re-implement) |

Nothing from the old UI's *functionality* is lost; only its *visuals and the 3D hero* are
discarded.

---

## 8. Execution order (each step independently runnable)

1. **Archive** current UI → `app/frontend/_archive_ui_v1/`. Add `index.html` fonts.
2. **`styles.css` + `theme.js`** — tokens, keyframes, dark-mode context. Unblocks all pages.
3. **`Navbar` + shared bits** (`ScorePill`, `Legend`, `ScoreRing`).
4. **Landing** — hero collage, discover, trust/stats, dark toggle.
5. **Explore** — sidebar + `MapCanvas` (Leaflet) + legend + popups.
6. **StoreDetail** — ring, sentiment bar, anomaly flag, live-sentiment composer, similar.
7. **Chat** — `ChatCore` wired to real `api.chat`; `MiniMap`; `ChatWidget`.
8. **Zones** — mode toggle, presets, real map overlay, metro/deep-link/fullscreen.
9. **Auth** — restyle.
10. **Full pass** — rebrand strings, favicon/title, run app, verify each flow against backend.

---

## 9. Open items / to confirm during build

- **Rebrand surface:** logo text, page `<title>`, favicon, footer, and any "ThriftFind" copy
  strings — all → FIRSTFIND. (`tf_token` / `tf_user` storage keys can stay; internal only.)
- **Hero copy & images:** DECIDED — keep the mockup's Unsplash image URLs as-is.
- **Anomaly flag:** frontend heuristic now; flag as a candidate for a real backend field later.
- **Dark mode coverage:** DECIDED — **app-wide**. The token remap applies to every page, with
  the toggle available in the shared Navbar; choice persisted in `localStorage`.

---

## 10. Definition of done

- App builds and runs; every route renders in the FIRSTFIND visual language.
- All five flows work against the **unchanged** backend: browse/filter map, open store, post a
  review (with async sentiment), chat with real intents + inline results + map + deep-link,
  explore AI zones and draw-radius clusters, log in/out.
- No "ThriftFind" strings remain in user-visible copy.
- Old UI preserved under `_archive_ui_v1/`.

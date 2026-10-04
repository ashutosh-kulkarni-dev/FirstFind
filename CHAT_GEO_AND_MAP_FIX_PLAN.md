# Chat Geo-Recognition & Map-Render Fix — Execution Plan

**Status:** approved scope, awaiting implementation. No code until the go-ahead.
**Two independent bugs, two independent tracks:**

- **Track A — Map does not render in chat** (frontend only; backend already correct).
- **Track B — Searches do not recognize geospatial locations** (backend; three sub-parts B1/B2/B3).

Tracks A and B share nothing. Either can ship alone. Within B, B1 → B2 → B3 is the
safe order but each is separable.

---

## Evidence (reproduced against the live DB, 105 stores w/ coords)

| Query | Current result | Verdict |
|---|---|---|
| `thrift stores in Koramangala` | area=Koramangala, map=Y | ✅ correct |
| `stores close to MG Road` | locality=`Shampura main road` | ❌ matched only on token "road" |
| `stores near me` | locality=`Near Merry Berry fashions,Jayanagar 4th Block` | ❌ "near me" is not a place |

Backend emits a `map` spec on **every** geographic reply (confirmed). So the map's
absence in the UI is 100% frontend. The geo mis-binding is 100% in
`chat/retrieval.py`. This plan is consistent with the deeper analysis in
[LOCATION_SEARCH_PLAN.md](LOCATION_SEARCH_PLAN.md) (defect: searchable vocabulary =
only the set of store `area` strings); B2 here is the "offline gazetteer" that plan calls for.

---

## Track A — Map renders in chat

**Root cause:** container width collapse.
`ChatCore` wraps `<MiniMap>` in `<div style={{ maxWidth:'78%' }}>` — max-width but
**no width**. Parent `.msg` is `display:flex; flex-direction:column;
align-items:flex-start`, which sizes children to *content* width. The MiniMap's inner
div is an empty block (intrinsic width 0), so the wrapper collapses to ~0px wide,
`L.map()` initializes at width 0, and the tile canvas is invisible. Store cards render
because `.msg-stores` is a grid whose card content gives it real width.

Files touched: **2** (`ChatCore.jsx`, `MiniMap.jsx`). No contract/API change. No deps.

- **A1.** [ChatCore.jsx:204-208](app/frontend/src/components/ChatCore.jsx#L204-L208) —
  change the map wrapper from `maxWidth:'78%'` to a real `width:'78%'` (mirror
  `.msg-stores`). This alone gives the container a resolved width.
- **A2.** [MiniMap.jsx:49](app/frontend/src/components/MiniMap.jsx#L49) — set the
  container div to `width:'100%'`; and in the effect
  ([MiniMap.jsx:21-46](app/frontend/src/components/MiniMap.jsx#L21-L46)) call
  `map.invalidateSize()` immediately after the tile layer is added, as a
  belt-and-braces correction for any deferred layout (e.g. while the chat pane is
  mid-scroll). No `invalidateSize` exists anywhere today.
- **A3** (secondary, independent). Metro pin never draws:
  `geo._nearest_metro()` returns `{name,line_name,line_color,distance_m}` with **no
  lat/lng**, but [MiniMap.jsx:39](app/frontend/src/components/MiniMap.jsx#L39) requires
  `metro.lat`. Fix by attaching `lat`/`lng` in
  [geo.py:70-75](app/backend/app/chat/geo.py#L70-L75) (the station dict already has
  them in scope). Backend-only, additive; skip if out of scope for this pass.

**Verify A:** run frontend + backend, open the full Chat page (`compact=false`), ask
"stores in Koramangala" → circle + store dots appear. The floating widget
(`compact=true`) intentionally hides the map — leave that gate as-is.

---

## Track B — Geospatial recognition

Design constraints (kept): no network in the request path, hard-filter-then-rank,
no silent substitution. All three sub-parts stay **inside `chat/`**; `geo.py`'s public
signature changes only additively (new optional `origin` arg).

### B1 — Stop the false positives (correctness; smallest, ship first)

**Root cause:** `_extract_locality_phrase`
([retrieval.py:123-141](app/backend/app/chat/retrieval.py#L123-L141)) accepts a match
on a **single** overlapping token of length >3. Generic words ("road", "main",
"block", "near") occur inside `locality_raw` values, so almost any query binds to a
bogus locality.

**Change (single function, no signature change):**
- Add a module-level `LOCALITY_STOPWORDS` set: `near, me, my, around, close, nearby,
  here, road, main, cross, stage, block, layout, nagar, phase, sector, opposite,
  next, behind, near-by, area, street, circle` (generic geo-filler that must never be
  the sole basis of a match).
- Tighten acceptance to require **one** of:
  1. full-phrase substring hit (already the strong case — keep), or
  2. **≥2** meaningful overlapping tokens, or
  3. exactly 1 overlapping token **only if** it is not in `LOCALITY_STOPWORDS`
     **and** length ≥ 5 (distinctive proper-noun tokens like "shampura" still work).
- Reject otherwise → returns `None` → the query honestly degrades instead of
  mis-binding.

**Effect:** "near me" → `None` (routes to B3); "MG Road" → no longer grabs
"Shampura main road" (then resolved by B2). Existing true positives (Koramangala,
Indiranagar, SG Palya, Tavrekere) unaffected — they hit case 1 or 2.

**Test:** unit table over the three evidence rows + 5 known-good areas. Pure function,
no DB writes; fast to assert.

### B2 — Recognize real places (additive coverage; one new file)

**Root cause:** recognizable vocabulary = only the strings present in
`Store.area`/`locality_raw`. Famous localities/roads not attached to a store
("MG Road", "Brigade Road", "Church Street"-as-road, "Cubbon Park") can't resolve.

**New isolated module `chat/places.py`** (imports nothing from `chat/`; leaf like
`contracts.py`):
- A curated static dict of Bengaluru landmarks/roads/localities →
  `{canonical: str, lat: float, lng: float, aliases: [str]}`. Start with ~30–50
  high-traffic entries; data lives in `data/bengaluru_places.json`, loaded once via
  `@lru_cache` (mirrors `geo._load_metro`).
- One public fn: `resolve_place(norm: str) -> Optional[PlaceHit]` where
  `PlaceHit = (canonical, lat, lng)`. Longest-alias-first substring match; no fuzzy
  network calls.

**Wiring — exactly two additive call sites, no rewiring:**
- `contracts.Entities`: add `place: PlaceHit | None = None` (frozen dataclass, default
  None → old code unaffected).
- `understand()` ([retrieval.py:213-228](app/backend/app/chat/retrieval.py#L213-L228)):
  after the existing `area`/`locality` extraction, if neither resolved, call
  `resolve_place(norm)`; set `entities.place` and force `intent="find_by_area"` when it
  hits. Precedence: **store-area exact > gazetteer > tightened locality fuzzy**.
- `geo._resolve_center()` ([geo.py:79-90](app/backend/app/chat/geo.py#L79-L90)): if
  `entities.place` is set, return its `(lat, lng)` directly (before the DB fallbacks).
  Everything downstream (`find_cluster`, metro, mapspec) already works off a center —
  no further change.

**Effect:** "MG Road" → real coordinates → correct cluster + map. Purely additive:
one new file, one new optional field, two call sites. Removing the file + the two
lines reverts cleanly.

### B3 — "near me" uses real device location (frontend + additive backend param)

**Root cause:** there is no location signal for "near me"; today it mis-binds
(fixed to `None` by B1). To make it *useful*, the browser must supply coordinates.

**Data flow (new, all additive):**

```
ChatCore.send()
  └─ (lazily) navigator.geolocation.getCurrentPosition()   [permission-gated, cached]
        └─ api.chat(message, origin?)                        origin = {lat,lng} | null
              └─ POST /api/chat { message, session_id, origin }
                    └─ ChatIn.origin: Optional[Origin]
                          └─ engine.respond(msg, db, user, session_id, origin)
                                └─ geo.locate(db, entities, origin)
```

- **schemas.py** `ChatIn`: add `origin: Optional[Origin] = None`
  (`Origin(BaseModel){ lat: float; lng: float }`).
- **routers/misc.py** [chat()](app/backend/app/routers/misc.py#L53-L62): pass
  `body.origin` into `chat_engine.respond(...)`.
- **engine.respond** ([engine.py:40-41](app/backend/app/chat/engine.py#L40-L41)): add
  `origin: Optional[tuple[float,float]] = None`; thread into the `CHAT_GEO` block
  ([engine.py:71-76](app/backend/app/chat/engine.py#L71-L76)) as `locate(db, entities,
  origin=origin)`.
- **understand()**: detect a "near me" phrase (`near me`, `close to me`, `around me`,
  `nearby`, `my location`) → set new `Entities.near_me: bool = False`.
- **geo.locate()** ([geo.py:97-128](app/backend/app/chat/geo.py#L97-L128)): if
  `entities.near_me and origin is not None`, use `origin` as the center directly
  (skip area/locality resolution). If `near_me` but no `origin`, return `None` so the
  handler replies honestly ("Share your location or name an area").
- **Frontend** `api.chat` ([api.js:97](app/frontend/src/api.js#L97)): accept optional
  `origin`, include it in the body when present. **ChatCore.send**
  ([ChatCore.jsx:107-128](app/frontend/src/components/ChatCore.jsx#L107-L128)):
  request geolocation once, cache the coords in a ref, pass on every call when granted.
  Permission denied / unsupported → send without `origin` (graceful).

**Privacy/robustness:** geolocation is opt-in by the browser; never blocks the send;
never persisted. `origin` is ignored unless `near_me` is set, so unrelated queries
never leak location into ranking.

---

## Sequencing & isolation summary

| Step | Files | New files | Contract change | Risk | Reverts by |
|---|---|---|---|---|---|
| A1+A2 | ChatCore.jsx, MiniMap.jsx | — | none | low | 2 line reverts |
| A3 | geo.py | — | none (additive dict keys) | low | 1 hunk |
| B1 | retrieval.py | — | none | low | 1 function |
| B2 | retrieval.py, geo.py, contracts.py, +places.py | places.py, bengaluru_places.json | +1 optional field | low | delete file + 2 lines |
| B3 | schemas.py, misc.py, engine.py, retrieval.py, geo.py, api.js, ChatCore.jsx | — | +optional `origin`/`near_me` | medium | additive, defaults off |

Ship order: **A (instant visible win) → B1 (kills false positives) → B2 (coverage) →
B3 (device location).** Nothing later depends on anything earlier except B3 reusing
B1's `near_me` routing.

## Test plan

- **A:** manual — full Chat page renders circle + dots for "stores in Koramangala";
  widget still hides the map.
- **B1:** unit table (pure fn): three evidence rows resolve to `None`/correct;
  5 known-good areas still resolve.
- **B2:** `resolve_place` unit tests for "MG Road", "Brigade Road", alias hits, and a
  miss; end-to-end `understand → geo.locate` returns a real center + non-empty cluster.
- **B3:** backend — `respond(origin=(...))` with a "near me" message returns a center
  == origin and a map; without origin returns the honest fallback reply. Frontend —
  permission granted vs denied both send successfully.

## Out of scope (explicitly)

- Restructuring `area` into a hierarchy / adding `geocode_precision` column
  (that's the larger [LOCATION_SEARCH_PLAN.md](LOCATION_SEARCH_PLAN.md) effort; this
  plan is the targeted bug-fix subset).
- Live Nominatim/geocoding in the request path.
- Changing the widget's deliberate no-map behavior.

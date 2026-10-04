# Shopping List / Trip Planner — Brainstorm (Deferred)

> Split out of `map-ux-brainstorm.md`. This is a **later** feature — not part of the initial 6-problem map UX pass. Kept here so the thinking isn't lost.

## Problem — Shopping List / Plan from Cluster Results

### What happens now
- After a cluster search, `Zones.jsx` renders the matching stores as a flat list of cards
- The list is read-only. The user can click through to a store, but there's no way to collect, save, reorder, or act on the set as a *shopping trip*
- `saveStore(id)` and the `Interaction` model (`kind: view/save/like`) already exist in the backend — individual saves are supported, but there's no concept of a *named list* or *route*

### Goal
> Turn the cluster's shop list into something the user can actually *use* for a shopping outing: pick the shops they want, save the set for later, and optionally get an ordered walking/metro plan through them.

### Sub-problems & options

#### a. Selecting shops from the cluster
- Each shop card gets a **checkbox / "+ Add"** toggle
- A running **"Your trip (n)"** tray/counter appears once ≥1 is selected
- Selected shops highlight on the map (brighter pin / numbered badge)
- Cheap, high-value first step — everything else builds on this selection set

#### b. Saving the list for future use

| Option | What it is | Persistence | Auth needed? | Effort |
|--------|-----------|-------------|--------------|--------|
| **A. localStorage (recommended first)** | Save named lists in browser | Survives refresh, single device | No | Low |
| **B. Backend `ShoppingList` model** | New table: `List(id, user_id, name)` + `ListItem(list_id, store_id, order)` | Cross-device, permanent | Yes | Medium |
| **C. Shareable URL** | Encode selected store IDs in a query param (`?trip=3,7,12`) | Link-based, no storage | No | Low |

- **Recommendation:** ship **A (localStorage)** immediately for a logged-out-friendly MVP, then add **B** for logged-in users (reuse the existing `Interaction`/save infra — a saved list is just a named collection of `save` interactions). **C** is a nice bonus for sharing a trip with a friend.
- A saved list needs: name (auto-suggest from area, e.g. "Indiranagar thrift run"), the store set, the radius/center used, and a timestamp.
- Surface saved lists on a new **"My Trips"** view or a drawer on the Zones page.

#### c. Building a shopping *plan* (ordered route)
Once shops are selected, help the user actually walk/ride between them:

**Option A — Simple nearest-neighbour ordering (recommended)**
- Order the selected shops greedily by proximity (start from the cluster center or nearest metro station, hop to closest unvisited shop each step)
- Draw a numbered polyline on the map: ① → ② → ③
- Show a plain itinerary list with walking distance between stops ("400 m · ~5 min walk")
- Purely client-side (haversine already exists), no external routing API, no cost
- Good enough for a "which order do I hit these shops" plan

**Option B — Real routing via OSRM / Mapbox Directions**
- Actual street-following walking routes + accurate times
- Pros: precise. Cons: external API, rate limits/keys, cost — overkill for an MVP

**Option C — Metro-aware plan**
- Group selected shops by nearest metro station, order stations along the line, then walk-clusters within each station's catchment
- Genuinely on-brand for ThriftFind (metro is the core premise)
- Build on top of A once the basic ordering works

**Decision:** Start with **A** (greedy nearest-neighbour + numbered polyline + itinerary), evolve toward **C** (metro-aware) since that's ThriftFind's differentiator. Skip **B** until users ask for turn-by-turn.

#### d. Extra "ease" features worth considering
- **Export / share:** copy trip as text, share link (b-C), or "Add to Google Maps" (open a Google Maps directions URL with the ordered waypoints — free, no API)
- **Time/budget estimate:** sum of `price_min–price_max` across selected shops → rough budget; est. total time = walking + browsing (~20 min/shop)
- **Open-now filter on the trip:** grey out shops that'll be closed by the time the user reaches them
- **"Optimize order" button:** re-runs the nearest-neighbour ordering
- **Reorder by drag:** let the user manually reorder itinerary stops (drag handles)
- **Check off as you go:** mark shops visited during the actual trip (ties back to the `view`/`save` interaction log)

### Suggested build order
1. **a** — selection checkboxes + trip tray (foundation)
2. **b-A** — save named trip to localStorage + "My Trips" drawer
3. **c-A** — nearest-neighbour ordering + numbered polyline + itinerary with distances
4. **d** — "Add to Google Maps" export + budget/time estimate
5. **b-B** — backend `ShoppingList` for logged-in cross-device sync
6. **c-C** — metro-aware planning (the differentiator)

### Open questions
- **Trip persistence for logged-out users** — is a localStorage-only MVP acceptable, or must trips require login (backend) from day one?
- **Route plan default** — optimize for shortest walking distance, or bias toward starting/ending at a metro station (ThriftFind's premise)?
- **"Add to Google Maps" export** — acceptable to hand off routing to Google Maps for turn-by-turn, or keep everything in-app?

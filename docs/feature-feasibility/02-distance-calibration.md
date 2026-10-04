# 02 — Distance Calibration (0–10 km Radius)

Covers: **Walkable Micro-Zones** (0.5–2 km), **Scooter Range** (3–6 km),
**Macro Sweep** (7–10 km), and the **text-input** for precise values.

Grounded against your stack: `GET /api/stores/nearby?lat&lng&radius_km`
(`stores.py:64-75`) already does a haversine radius scan sorted by distance, and
`config.py` already holds `LOCATION_RADIUS_KM`. The plan even lists a radius
control (`1 / 2 / 3 / 5 km`) as an accepted UI element.

---

## The uncomfortable answer first

The radius slider is the single most trivially feasible thing in your whole spec
— it's a query parameter that already exists. But a **straight-line (haversine)
radius is a lie in Bengaluru**, and your own spec already knows this (you ask for
a travel-time overlay in file 04). A "3 km" circle that crosses the Outer Ring
Road or Silk Board is not 3 km of reachable shops. So: ship the km slider now
(easy), but don't oversell "3 km" as meaning anything until the travel-time work
in files 03/04 lands.

---

## Feasibility

### The slider itself, all three bands — **[Certain] trivial**

Walkable (0.5–2 km), Scooter (3–6 km), Macro (7–10 km) are **not three
features** — they are three labelled ranges of one float you already pass to
`nearby`. HDBSCAN doesn't even need to run for Mode B; the radius *is* the hard
filter. Effort: the slider UI + binding. Hours.

The band *names* ("Walkable / Scooter / Macro") are a UX veneer over the same
number — and a good one. That maps cleanly onto the "Transport presets" idea
already ranked in `ZONAL_STORE_HOPPER_PLAN.md` (#3: Walking→1 km, Auto/bike→3–5
km). Build the named presets and the raw slider as one control.

### Text input for precise values ("1.5 km") — **[Certain] trivial**

A number field bound to the same `radius_km`. The only work is validation (clamp
to 0–10, reject junk). Your instinct that sliders feel fidgety on mobile is
**[Likely] correct** — dual control (slider + text) is standard and cheap.

### Macro Sweep (7–10 km) — **[Certain] feasible, [Likely] low value at current data**

Mechanically identical to the others. But a 10 km radius over 48 city-wide stores
returns "most of the catalogue in a big circle," which isn't a *sweep of active
pockets* — it's a dump. The Macro band only becomes meaningful when paired with
**Mode A discovery** (the precomputed named pockets), so "macro" shows *clusters*
across the city, not a flat radius of every pin. Wire the Macro band to the
discovery view, not the raw radius, or it underdelivers.

---

## The real limitation (be honest with users about this)

`haversine_km` (`utils.py`) is **great-circle distance** — a straight line
ignoring roads, flyovers, one-ways, lakes, and traffic. In Bengaluru the gap
between crow-flies km and real reachability is large and *direction-dependent*.
Consequences for the slider:

- **[Certain]** the circle is geometrically correct and cheap.
- **[Likely]** two shops equidistant on the map can be 5 min and 40 min away.
  The slider can't know that without a routing/travel-time layer.
- Fix path is already in your spec: the **Travel-Time Overlay** (file 04) and
  **traffic-bottleneck-aware clustering** (file 03). Those are the hard parts;
  the km slider is the easy part that makes them *look* solved when they aren't.

My advice: ship the km slider labelled honestly as "map distance," and gate any
"~12 min away" language on the file-04 travel-time work actually being wired.

---

## What I need from you (can't get reliably from web search)

1. **The default radius and the exact band cutoffs you want.** Product call, not
   research. I'd propose: default 2 km; Walkable ≤2, Scooter 3–6, Macro 7–10 (as
   you wrote). Confirm or override. `config.py` has `LOCATION_RADIUS_KM` — tell me
   the number.
   Answer: this is perfect

2. **Snap-to-preset vs free slider vs both.** Do you want the slider to snap to
   the three named bands, move freely 0–10, or both (named buttons + free
   slider + text box)? I recommend all three surfaces on one value. Your call
   sets the UI.
   Asnwer: All three, neatly arranged

3. **Whether "radius" means map-distance or travel-time in v1.** This is the one
   that matters. If v1 is pure haversine (my recommendation — ship fast, label
   honestly), I need you to accept that "3 km" is crow-flies. If you want radius
   to mean *reachable* distance from day one, that's not this file — it depends
   entirely on the routing data I ask for in files 03 and 04, which you must
   source. Pick: honest-map-distance now, or wait for travel-time.
   Answer: Radius means map distance. 
           The raidus should be used for the zones feature
           travel time is something I want to add to the conversational chatbot, whch can help users plan their shopping experience. FOr this, we sould use road distance. Also , I will provide a sort of dataset for travel time (unstructured ) which can be roughly used withr espect to area and timings during the day for user user travel plans.

4. **Nothing else.** Unlike the other files, the radius slider needs no private
   data from you beyond the config numbers above. The coordinates and haversine
   are already in the app. This one is genuinely just a build decision.
   Answer: okay
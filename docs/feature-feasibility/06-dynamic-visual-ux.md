  # 06 — Dynamic Visual UX

Covers: **Real-Time Split/Merge Preview** (clusters visually split/merge as the
radius slider moves) and **Neighborhood Snap** (radius snaps to ward/neighbourhood
boundaries instead of a mathematical circle).

Grounded against your stack: Leaflet dark map (`Zones.jsx`), HDBSCAN clustering,
haversine `nearby`, the *actual-radius circle* fix already scoped in
`ZONAL_STORE_HOPPER_PLAN.md` (replacing the hard-coded 2200 m at `Zones.jsx:34`),
offline principle, ~48 stores.

---

## The uncomfortable answer first

**Real-Time Split/Merge is feasible and mostly a performance/UX problem, not a
data problem — build it.** **Neighborhood Snap sounds simple and is actually the
harder of the two, because "snap to a ward boundary" requires ward-boundary
polygons you don't have in the app and which aren't cleanly scrapable — it's the
same boundary-data problem as file 03's barriers.** Don't assume the flashier
feature (split/merge) is the hard one; it's the quiet one (snap) that needs data
you must source.

---

## Feasibility

### Real-Time Split/Merge Preview — **[Likely] feasible; performance is the real question**

As the radius slider moves, clusters merge into super-hubs or split into
sub-zones live on the map. The clustering to support this is the **same HDBSCAN
primitive** plus the recursive sub-clustering from file 01's honest `max_shops`
split. The engineering questions are about *responsiveness*, not possibility:

- **Where does recompute happen?** Two options:
  - **Server round-trip per slider change** — clean, reuses backend clustering,
    but laggy and chatty; a slider dragged across 0–10 fires dozens of requests.
    Needs debouncing. **[Likely]** feels sluggish for a "real-time" promise.
  - **Client-side clustering** — ship the (few dozen) store coords to the browser
    once and cluster in-JS as the slider moves. **Recommended for the "real-time"
    feel.** At 48–500 stores this is trivial for the browser. Libraries like
    Leaflet.markercluster or a small JS DBSCAN handle it at 60fps. Above a few
    thousand stores you'd revisit.
- **Consistency risk [Likely]:** if client-side JS clustering and server-side
  HDBSCAN disagree, the *preview* won't match the *result* the user gets on
  release. Decide: is the slider a live *preview* (client approximation) that
  commits to a server cluster on release, or is the client the source of truth?
  I'd make it a preview that commits — but you must accept minor preview/result
  drift or unify the algorithm.

At your data volume this is a **[Likely] few-days frontend feature**, and it's
genuinely good — it's the thing that makes the density/radius sliders feel alive
instead of abstract. It reuses the `max_shops` split engine from file 01, so
build those together.

### Neighborhood Snap — **[Guessing→Likely] feasible only if you get boundary polygons**

"Snap the radius to recognised ward/neighbourhood boundaries rather than strict
circles." The appeal is obvious — a blob shaped like *Indiranagar* reads better
than a circle bleeding into three localities. But a circle is math you already
have; a **ward/neighbourhood shape is a polygon dataset you don't.** Specifically:

- You need **BBMP ward boundaries** (or neighbourhood polygons) as GeoJSON. This
  is not in your app, and while some Bengaluru ward GeoJSON exists in open-data
  circles, it's **inconsistent, sometimes outdated (ward counts and boundaries
  have been redrawn), and not something to trust from a random scrape.** Treat it
  as an asset to source and verify, like the file-03 barrier layer.
- With polygons in hand, "snap" = point-in-polygon: find the ward containing the
  center, show that ward's shape, filter shops inside it. Deterministic, offline,
  cheap **once the data exists.** Leaflet renders GeoJSON natively.
- **Alternative that needs no polygons [Likely] and I'd ship first:** "snap" to
  your *own* area groupings — the `area` / `locality_raw` values you already
  canonicalise (`LOCATION_SEARCH_PLAN.md`). Instead of a true ward polygon, draw
  a hull around the stores tagged to that area. Not a real administrative
  boundary, but it uses data you own and gives 70% of the visual benefit with
  zero new dataset.

I disagree with leading with true ward-boundary snap. **Instead:** ship
"area-hull snap" from your existing `area` tags first; add real ward polygons only
if you decide the administrative accuracy is worth sourcing and maintaining the
GeoJSON. **The risk** with real ward polygons is you adopt a boundary file that
goes stale (wards get redrawn) and your map silently shows wrong neighbourhoods —
worse than an honest hull around your own data.

---

## Shared note

Both features amplify the **actual-radius circle** fix already in your plan
(`Zones.jsx:34` hard-coded 2200 m → real per-cluster radius). Do that fix first;
it's the foundation both of these sit on. Split/merge needs real radii to look
right; snap replaces the circle entirely.

---

## What I need from you (can't get reliably from web search)

1. **Preview-vs-truth decision for Split/Merge.** Is the moving slider a
   *client-side preview* that commits to the server's authoritative cluster on
   release (my recommendation — fast, accept minor drift), or must preview and
   result be byte-identical (then we run one algorithm in one place, slower)?
   This is an architecture call only you can make; it's not searchable.

2. **Client-side vs server-side clustering appetite.** Are you OK shipping store
   coordinates to the browser for live in-JS clustering? For a public thrift
   directory that's fine (the data's already on the map), but it's your call on
   whether any store data is sensitive. Confirm.

3. **For Neighborhood Snap: which boundaries, and will you source/maintain the
   GeoJSON?** Do you want (a) true BBMP ward polygons (you or I source a GeoJSON,
   *you* commit to keeping it current as wards change), or (b) area-hulls from
   your own `area` tags (I recommend this for v1, no external data)? If (a), I
   need you to own the "is this boundary file still current?" question, because a
   stale one ships wrong neighbourhoods.

4. **Your target store scale (again).** Client-side real-time clustering is
   trivial at 48–500 stores and needs rethinking in the thousands. Same question
   as files 01–03 — tell me the trajectory once and it settles the design for all
   of them.

  Answer: The cluster should start from the zone the user wants.TH user should be able the the cluster, maybe evn move the cluster, edit the parameters of the xluster (min / max shop , etc ) , to enhance user experience
# 01 — Density Controls (Min & Max Shops)

Covers: **Thrift Crawl Mode** (high min), **Decision Fatigue Shield** (max cap),
**Solo Gem Hunting** (min = 1).

Grounded against your stack: HDBSCAN geo-clustering (`ml/zones.py`), haversine
radius search (`GET /api/stores/nearby`), the store-hopper reframe already
written up in `ZONAL_STORE_HOPPER_PLAN.md`. All three of these are the **same
control** — `min_shops` / `max_shops` on the `find_cluster()` primitive — wearing
three product names.

---

## The uncomfortable answer first

`min_shops` is trivially feasible. `max_shops` is **not the feature you think it
is**, and if you build it the naive way it will produce a worse map, not a
cleaner one. Detail below under Decision Fatigue Shield.

---

## Feasibility

### Thrift Crawl Mode — high minimum (4–6 shops) — **[Certain] trivial**

This is already 90% built. `ZONAL_STORE_HOPPER_PLAN.md` specifies
`find_cluster(center, radius_km, min_shops)` with an "honest-empty + widen"
response. A high `min_shops` is just a parameter value. The radius search in
`stores.py:64-75` returns the in-radius set; you count it against `min_shops` and
either return the cluster or say "only 3 within 2 km, widen to 4 km?".

Effort: hours, not days. It's a slider bound to an integer you already pass down.

One correctness note: "guarantees a dense area" is **[Likely] false as stated**.
A high `min_shops` doesn't *create* density — it *filters out* sparse areas. If
Koramangala has 6 shops in 1.5 km you get a crawl; if the user's chosen center
doesn't, you get an honest empty. That's the right behaviour, but market it as
"only show me areas dense enough to walk," not "guarantees density."

### Decision Fatigue Shield — max cap (e.g. 8 shops) — **[Likely] feasible, wrong default design**

Two ways to implement a max, and they behave very differently:

1. **Truncate:** find all shops in radius, keep the 8 nearest, drop the rest.
   Cheap, but you're now *hiding real shops* from the user with no signal. The
   9th shop 50 m past the 8th just vanishes. That's a silent-substitution
   violation of your own locked chatbot principle (`CHATBOT_RETRIEVAL_PLAN.md`).
2. **Sub-cluster / split:** when a radius holds >max shops, run the clustering
   *again inside it* at a tighter scale so one dense hub (Commercial Street)
   becomes 2–3 walkable sub-zones of ≤8 each. This is the honest version and it's
   the same HDBSCAN primitive at a smaller `min_cluster_size`.

I disagree with a plain truncation cap. **Here's what I'd do instead:** treat
`max_shops` as a *split trigger*, not a *hide filter*. Above the cap, split the
hub and show the user "this pocket is big — here are 3 walkable sub-zones" rather
than amputating shops 9–25. The risk in a truncate cap is that your densest,
most valuable areas (exactly the ones a thrifter wants) are the ones you
mutilate.

Effort for the honest version: **[Likely] 1–2 days** (recursive re-cluster +
map/UX for sub-zones). This is the same engine as the "Real-Time Split/Merge
Preview" idea in file 06 — build them together.

### Solo Gem Hunting — min = 1 — **[Certain] trivial, mostly a copy change**

`min_shops = 1` means "don't filter out isolated boutiques." Already the default
behaviour of a radius search — a lone shop in range is returned. The only real
work is making sure your *discovery* view (Mode A, the precomputed pockets) has a
floor of ~3 and doesn't hide singletons; the plan already flags this open
question ("minimum stores to count as a pocket?", `ZONAL_STORE_HOPPER_PLAN.md`
Decisions #2). Decide the floor and expose min=1 as an explicit "include solo
shops" toggle so users know they're opting out of the crawl logic.

---

## Cross-cutting risk you should decide now

Your live DB has **48 coordinate-bearing stores across the whole city**
(`ZONAL_FEATURE_CURRENT.md`). A min of 4–6 shops inside a 1.5 km circle is a
*high bar at this data volume* — most centers will return honest-empty. The
feature is correct, but at 48 stores it will feel like it "never finds anything"
unless your catalogue grows. **[Likely]** this is a data-density problem, not a
code problem, and no amount of slider work fixes it. See "what I need from you"
#1.

---

## What I need from you (can't get reliably from web search)

1. **Your real, current store count with coordinates — and the near-term
   trajectory.** The docs say 48 live / 131 referenced. The min-shops feature is
   only meaningful if enough shops sit within walking radius of each other. I
   can't scrape your private catalogue. Give me: how many coordinate-bearing
   stores today, and are you at 48 or heading to 500+ this quarter? This decides
   whether "min 4" is a sensible default or a guaranteed empty screen.
   Answers: leave the coordinates. I have to update a lot of them. for now focus in the system

2. **Default and boundary values you want.** These are product calls, not
   research answers. I need your intended: default `min_shops` (I'd say 3),
   default `max_shops` / split trigger (I'd say 8), and the discovery-view floor
   (I'd say 3). Tell me if you disagree with those and why.
   Answers: okay, do this. split on the trigger.

3. **The behaviour when a cap splits a hub.** When Commercial Street exceeds the
   cap, do you want (a) auto-split into named sub-zones, (b) show all + a "too
   many, tap to split" prompt, or (c) truncate to nearest N (I advise against
   this). Your answer sets the build.
   Asnwers: b

4. **Whether "solo gem" shops are flagged in your data.** If you have a field
   marking curated studios / appointment-only boutiques, min=1 can surface them
   deliberately. If not, min=1 just means "no density filter." Do you tag these?
   no
# User-Editable Features — Feasibility & Data Needs

Feasibility assessment for the ThriftFind "user editables," grounded against your
actual backend (`ZONAL_STORE_HOPPER_PLAN.md`, `LOCATION_SEARCH_PLAN.md`,
`BACKEND_OVERVIEW.md`, `ZONAL_FEATURE_CURRENT.md`): FastAPI + SQLAlchemy, HDBSCAN
geo-clustering, haversine `nearby`, offline/token-free retrieval, ~48–131
Bengaluru stores, area-centroid location resolution. **No transit, traffic,
sidewalk, parking, routing, or boundary data currently in the app.**

One file per category:

- `01-density-min-max-shops.md`
- `02-distance-calibration.md`
- `03-hyper-local-traffic-bottleneck.md`
- `04-value-add-ux-enhancements.md`
- `05-social-personalization.md`
- `06-dynamic-visual-ux.md`

Each file leads with the uncomfortable answer, tags claims `[Certain]` /
`[Likely]` / `[Guessing]`, and ends with the specific inputs I need from you that
web search can't reliably supply.

---

## Feasibility at a glance

| Feature | Feasibility | Build order | Blocker |
|---|---|---|---|
| One-Tap Presets (04) | Trivial | **1st — free win** | Preset values (product call) |
| Min shops / Thrift Crawl (01) | Trivial | 1st | Store density; defaults |
| Radius slider + bands (02) | Trivial | 1st | Config numbers only |
| Solo min=1 (01) | Trivial | 1st | Discovery floor decision |
| Save & Share Routes (05) | Moderate | 2nd | Schema + privacy defaults |
| Metro Alignment (04) | Feasible (offline) | 2nd | Verified station list |
| Real-Time Split/Merge (06) | Feasible (perf) | 2nd | Preview-vs-truth call |
| Max-shops cap (01) | Feasible, **redesign** | 2nd | Split, don't truncate |
| Travel-Time Overlay (04) | Estimate only | 3rd | Accept "~est" or pay for API |
| Neighborhood Snap (06) | Needs boundary data | 3rd | Ward GeoJSON or area-hull |
| Traffic Bottleneck (03) | Hard; approximate | Later | Your barrier list + windows |
| Parking/Auto filter (04) | Code easy, **data hard** | Later | Per-store data you must collect |
| Community Presets (05) | Feasible, **UGC ops** | Later | Moderation owner; user volume |
| Walkability Index (04) | Weakest | Later | No sidewalk data exists |

---

## The four things that unblock the most

Most of the "what I need from you" questions collapse into four:

1. **Real store count + trajectory.** Are you at 48 or heading to 500+? This
   decides whether min-shops/radius defaults are sensible or guarantee empty
   screens, and whether client-side real-time clustering (06) stays trivial.
   Recurs in files 01, 02, 03, 06.

2. **Offline principle: hold or break it?** Travel-time (04), traffic
   bottlenecks (03), and live ETAs all collide with your locked token-free/no-
   network rule. Default assumption unless you say otherwise: **stay offline, use
   estimates and static flags.** One decision settles three features.

3. **Local knowledge you hold and search doesn't.** The barrier "looks-close-but-
   isn't" pairs and their bad-traffic time windows (03) are the single most
   valuable input you can give — they *are* the traffic feature. Rough is fine.

4. **Per-shop data you must collect.** Parking/auto (04) and walkability (04) are
   afternoon-sized code features sitting on datasets that don't exist and can't
   be scraped reliably. If you'll populate the fields (your `Thrift Stores.xlsx`
   is the natural home), they ship; if not, they can only be stubbed.

My recommendation: ship the "1st" row (presets + sliders) this week — it's nearly
all built and makes the whole control panel feel real — then work down the table.
Don't start with traffic, walkability, or the community gallery; they're the
lowest value-per-effort at your current data volume.

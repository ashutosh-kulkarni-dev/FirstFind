# Chatbot Enhancements — Next Stage (DEFERRED)

**Status:** parked. Do **not** build until the zonal feature
(`ZONAL_FEATURE_SCOPE_v1.md`) ships. Everything here lives in the **conversational
chatbot**, uses **road distance / time-of-day** (not map distance), and depends on
**data you will provide**. None of it touches zonal clustering.

**Grounded against:** `chatbot.py` (rule-engine, `zone_exploration` intent
`447-469`, `_extract_area` `120`, offline draft + optional Groq phrasing),
`BACKEND_OVERVIEW.md`, `CHATBOT_RETRIEVAL_PLAN.md` (token-free / offline /
hard-filter-then-rank / honest-empty — all preserved below).

**Hard dependency:** two of the three features are **blocked on your datasets.**
Until those exist, only the metro asset can proceed. You said "for now, focus on
clustering" — so this doc exists to lock the *design* and the *exact data shape*
so that when you hand the files over, there's zero re-litigation.

---

## Feature 1 — Travel-time planning (road distance, chatbot only)

**What:** in conversation, help a user plan a shopping trip using *rough road
travel time* between areas, varying by time of day. Not a live ETA, not in the
zonal map.

**Your decision (file 02):** radius stays map-distance for zones; travel-time is a
chatbot-only planning aid built from an **unstructured dataset you'll provide**,
used roughly per area × time-of-day.

**How I'd use your unstructured data:**
- At **seed/pipeline time** (offline, never in the request path), parse your file
  into a lookup table. Target normalized shape:
  ```
  travel_time[(area_a, area_b, daypart)] = rough_minutes
  # daypart ∈ {morning_peak, midday, evening_peak, night}
  ```
  or, if your data is per-area rather than pairwise:
  ```
  area_congestion[(area, daypart)] = slowdown_factor   # multiply a base est.
  ```
- At **request time**, the chatbot looks up the pair/area + current or user-stated
  daypart and phrases: *"Indiranagar → Koramangala is ~25 min now (evening peak);
  ~12 min if you go after 8pm."* Pure dict lookup + the existing offline draft →
  Groq only rephrases (`chatbot.py:548`). **Zero network, token-free.**
- Honest-empty preserved: if the pair isn't in your data, say so
  (*"I don't have a travel-time read on that stretch"*) — never invent a number.

**What I need from you (blocking):** the dataset. Any messy form is fine — a
spreadsheet, a bullet list, notes — as long as it carries **(area or area-pair) ×
(time window) × (rough minutes or "slow/ok/fast")**. I'll structure it. Without
it, this feature cannot start.

---

## Feature 2 — Traffic-bottleneck warnings (chatbot only)

**What:** warn users away from known Bengaluru bottlenecks at bad times —
*"heads up, that route crosses Silk Board; brutal 5–9pm. Go anyway?"* Advisory,
not a hard block.

**Your decision (file 03):** no live routing (too heavy), no barrier-aware
*clustering*. Instead a **cheap Bengaluru bottleneck dataset you'll provide**,
used **purely in the chatbot** to recommend avoiding those areas at those times
"unless they really want to."

**How I'd use your unstructured data:**
- Seed-time parse into:
  ```
  bottlenecks[name] = {
    where: [area/segment names or a rough coord/point],
    bad_windows: [{days, start, end}],   # e.g. Mon–Fri 08:00–11:00, 17:00–21:00
    severity: "high" | "medium"
  }
  ```
- Request-time: if a planned crawl / mentioned route touches a bottleneck area
  during a bad window (compare against `is_open_now`'s IST clock, `utils.py:53`),
  the chatbot appends a **soft warning + an alternative or a "go anyway"**. Never
  removes shops; never blocks. Offline dict lookup.
- Explicitly **not** fed into zonal clustering (your instruction) — this is a
  conversational advisory layer only.

**What I need from you (blocking):** the bottleneck list — **which** choke points,
**where** they are (area names are enough; coords better), and **when** they're
bad. Rough is fine; your lived/local knowledge beats any scrape here.

---

## Feature 3 — Metro routing (chatbot only)

**What:** beyond the zonal *proximity overlay*, let the chatbot answer *"what's the
best metro station for a thrift trip from <my start>?"* and route along the line.

**Your decision (file 04):** if the user names a station → shops near it (this
part is the zonal overlay, already in `ZONAL_FEATURE_SCOPE_v1.md`). Else → offer
"best metro station/route from your start point" and use the nearest metro point.

**How I'd build it (offline, no blocking dataset — I build the asset):**
- Reuse `data/metro_stations_blr.json` (Purple + Green) from the zonal doc, and
  add **line topology**: station order per line + interchange stations. That's a
  small static graph.
- Chatbot flow:
  1. User gives a start (area centroid or GPS).
  2. Nearest station = haversine min over the station asset.
  3. "Best station for shops" = station whose 1 km radius holds the most
     (proximity-ordered) shops, optionally along the user's line.
  4. Simple path over the line graph for "which stations to ride." No external
     routing service.
- Token-free, offline, deterministic. **This is the only next-stage feature not
  blocked on your data** — it needs the curated station+line asset, which I build
  and you sign off.

---

## Integration point (when this stage starts)

Rewrite the `zone_exploration` intent (`chatbot.py:447-469`) — currently routes
only to Budget/Hidden by keyword — around the new primitives, keeping the return
contract `{reply, intent, stores, suggestions}` (`chatbot.py:550`) unchanged so
the Groq phrasing step and frontend need no shape change. Broaden triggers
(`chatbot.py:51,65`) for "how long to get to," "avoid traffic," "metro to,"
"best station." Add offline regex extractors for time-of-day and station names.

---

## Locked principles (unchanged from your existing docs)

- **Offline / token-free in the request path.** All three are dict lookups on
  seed-time-parsed assets; Groq only rephrases the final draft.
- **Honest-empty, no invention.** Missing travel-time / unknown bottleneck / no
  station → say so, never fabricate.
- **Advisory, not gating.** Traffic warnings and travel-time inform; they never
  remove shops or block a plan.
- **No live traffic API** unless you later explicitly accept a paid, cached,
  online dependency (default: never).

---

## Start conditions (checklist before this stage begins)

1. Zonal feature v1 shipped.
2. You've handed over the **travel-time dataset** (area/pair × time × minutes).
3. You've handed over the **bottleneck dataset** (choke point × where × when ×
   severity).
4. Metro station+line asset built and signed off (I draft, you verify).

Items 2 and 3 are the true blockers — the features are designed and waiting; they
need only your data to become real.

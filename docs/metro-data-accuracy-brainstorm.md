# Metro Data Accuracy — Diagnosis & Plan

> Spun out of Problem 3 in `map-ux-brainstorm.md`. Goal: the metro map must be
> **accurate today** and **self-update** when new lines become operational, without
> hammering public Overpass on every client page load.

---

## Part 1 — What actually went wrong (answering "was it the sources, or me?")

**It was me, not your sources.** Two separate, compounding failures — both on the
implementation side:

### Failure A — The shipped JSON is stale, hand-authored data (never regenerated)

`data/metro_stations_blr.json` is marked `"_reviewed": "2024-12"` and was
**hand-typed**, not produced by the pipeline. It contains provably wrong data:

| Symptom | Evidence in `metro_stations_blr.json` |
|---|---|
| Purple line has a **Green-line station spliced in** | `Silk Institute` (12.8508, 77.6032) appears as Purple `order 27`, then Purple jumps to `Trinity` (12.9724, 77.6068) at `order 28` — a ~13 km teleport. Silk Institute is the **Green** line south terminus, not on Purple. |
| **Fabricated Whitefield stretch** | `Doddathoguru`, `Sitharampalya`, `Wadeyaranagara`, `Cast Iron Bridge` (orders 37–43) are **not real Purple Line stations**. The real eastern stops are Nallurhalli → Kundalahalli → Seetharampalya → Kadugodi Tree Park → Channasandra → Pattandur Agrahara → Whitefield (Kadugodi). |
| **Order field is internally inconsistent** | Ordering breaks the line geometry, so `L.polyline` draws visible zig-zags. |

So the map looked wrong because it was rendering **bad input**, regardless of source quality.

### Failure B — The pipeline that *should* replace it has a fatal ordering bug

`scripts/refresh_metro.py` already exists (the Overpass approach — Option 1 — was
partly built). But it orders stations like this:

```python
# scripts/refresh_metro.py, ~line 237
if line_id in ("purple", "yellow", "blue"):
    unique.sort(key=lambda s: s["lng"])   # ← sort by longitude
else:
    unique.sort(key=lambda s: -s["lat"])  # ← sort by latitude
```

**This is the core bug.** A metro line is a *curved path*, not a monotonic line in
lat or lng. The Purple Line, for example, runs west→east but **dips south** through
Jayanagar/Banashankari and **curves north** through Baiyappanahalli. Sorting purely
by longitude reorders those stations into nonsense, producing the same zig-zag
polyline. No amount of better source data fixes this — the sort throws the ordering
away.

**The fix is to stop re-deriving order and instead preserve OSM's own member order.**
An OSM `route=subway` relation lists its stops **in physical travel sequence**. If we
read members in the order Overpass returns them (and don't re-sort), the line is
correct by construction.

### Bonus bugs in the current pipeline (fix while we're here)

- `clean_name()` regex `\s*(metro|station|stop)\s*` will mangle legitimate names like
  **"City Railway Station"** → "City Railway" and **"Silk Institute"** is fine but
  **"Metro Cash & Carry"**-style names would break. Tighten to strip only trailing
  `" metro station"` / `" (metro)"`.
- Overpass `out body; >; out skel qt;` returns node geometry but member `role`
  strings vary (`stop`, `stop_entry_only`, `stop_exit_only`, `platform`,
  `platform_entry_only`…). The `role in ("stop","platform","station")` substring
  check is OK, but we should prefer **`stop*` roles only** for the station list and
  ignore `platform*` duplicates rather than dedup-by-distance after the fact.
- `deduplicate_stations()` uses a flat-earth approximation and a 50 m threshold — fine
  for Bengaluru, but interchange stations (Majestic on both lines) must **not** be
  merged across lines. It currently dedups per-line only, which is correct — keep it.

---

## Part 2 — Which option is easiest? (your three choices)

You asked me to pick the **easiest to implement** among:

1. **Live OpenStreetMap Overpass API** (with a weekly cron → static GeoJSON on CDN)
2. **Official BMRCL Static GTFS via IUDX**
3. **Open-source boilerplates / repositories**

### Recommendation: **Option 1 (Overpass + weekly cron), fixed.** ✅

Here's the honest comparison:

| | 1. Overpass + cron | 2. BMRCL GTFS via IUDX | 3. OSS boilerplate |
|---|---|---|---|
| **Setup effort** | **Low** — 90% already built (`refresh_metro.py` + `metro-refresh.yml` exist). Just fix the ordering bug. | High — IUDX needs account registration, API keys, dataset discovery, GTFS parsing (`stops.txt`, `routes.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt`). | Medium — find a repo, verify freshness, adapt schema, then still maintain it. |
| **Accuracy today** | Good. OSM Namma Metro coverage is complete & actively edited by locals. | Best-in-class *if* the dataset is published & current — but BMRCL GTFS availability on IUDX has historically been **patchy/stale**. | Depends entirely on the repo; usually a **snapshot** that rots. |
| **Auto-updates when new lines open** | **Yes** — OSM editors add stations days after opening; weekly cron picks them up. | Yes *if* BMRCL republishes GTFS promptly (not guaranteed). | **No** — static snapshot, requires you to notice and re-import. |
| **Line geometry (polyline shape)** | Excellent — OSM relations carry ordered members **and** a `shapes`-equivalent way geometry we can use for smooth curved lines, not just station-to-station straight segments. | Excellent — GTFS `shapes.txt` is purpose-built for this. | Varies. |
| **Ongoing maintenance** | Near-zero (cron + PR review). | Medium — API keys expire, IUDX endpoints change. | High — manual. |
| **Licensing** | ODbL (attribute "© OpenStreetMap contributors"). | Open Govt Data License (check terms). | Varies. |

**Why not GTFS (Option 2)?** GTFS is technically the "official path" and would be
lovely, but IUDX onboarding + key management + parsing 5 CSVs is strictly *more* work
than fixing a bug in code we already wrote — and its freshness guarantee is weak in
practice. It fails the "easiest" test.

**Why not OSS boilerplate (Option 3)?** It doesn't satisfy your hard requirement:
"update when new lines become operational." A checked-in snapshot can't self-refresh.

**Verdict:** Fix Option 1. It's the least code, it self-updates, and the failing
piece was *our ordering bug*, not the data source.

---

## Part 3 — The fixed Overpass pipeline (concrete changes)

### 3.1 — Preserve OSM member order (the real fix)

Do **not** sort by lat/lng. Read the relation's members in the order Overpass returns
them and keep that order:

```python
def extract_stations_in_order(relation, node_lookup, node_names):
    """Walk relation members IN ORDER, keeping only stop* roles once each."""
    stations = []
    seen_names = set()
    for member in relation.get("members", []):
        if member["type"] != "node":
            continue
        role = member.get("role", "")
        if not role.startswith("stop"):     # stop, stop_entry_only, stop_exit_only
            continue
        nid = member["ref"]
        if nid not in node_lookup:
            continue
        name = clean_name(node_names.get(nid, ""))
        if name in seen_names:              # skip entry/exit duplicates of same stop
            continue
        seen_names.add(name)
        lat, lng = node_lookup[nid]
        stations.append({"name": name, "lat": round(lat, 6), "lng": round(lng, 6)})
    # order = member sequence; assign 1..N as-is, DO NOT re-sort
    for i, s in enumerate(stations):
        s["order"] = i + 1
        s["phase"] = "operational"
    return stations
```

> Namma Metro relations are usually split by **direction** (e.g. "Purple Line:
> Whitefield → Challaghatta" and the reverse). Pick the forward direction per line
> (longest member list, or a fixed direction tag) so we don't get each station twice
> in mirrored order. Merge multiple `reach` sub-relations by concatenating in
> geographic sequence, not by re-sorting.

### 3.2 — Fix `clean_name()` so it doesn't eat real words

```python
def clean_name(name: str) -> str:
    n = re.sub(r"\s*\(?metro\)?\s*$", "", name, flags=re.I)      # trailing "Metro"
    n = re.sub(r"\s+metro\s+station$", "", n, flags=re.I)         # "… Metro Station"
    return n.strip() or "Unknown"
# "City Railway Station" is preserved; only metro-specific suffixes are stripped.
```

### 3.3 — Capture line geometry for smooth polylines (optional, high polish)

Also pull the relation's `way` members and emit their ordered node coordinates as a
`"path": [[lat,lng], …]` per line. Then `L.polyline(line.path)` draws the **actual
track curve** instead of straight station-to-station hops. Falls back to station
coords if `path` is absent — renderer stays backward compatible.

### 3.4 — Add a validation gate before writing (catch bad refreshes)

Before overwriting the JSON, assert sanity so a broken Overpass response never ships:

```python
def validate(result):
    for line in result["lines"]:
        sts = line["stations"]
        assert len(sts) >= 5, f"{line['id']}: too few stations ({len(sts)})"
        # no giant jumps between consecutive stations (catches ordering bugs)
        for a, b in zip(sts, sts[1:]):
            jump = haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
            assert jump < 4.0, f"{line['id']}: {a['name']}→{b['name']} jump {jump:.1f}km"
```

This assertion **would have caught the Silk Institute→Trinity teleport** in the
current data. It's the cheapest insurance against a silent regression.

### 3.5 — Cron → committed JSON (already correct, keep it)

`.github/workflows/metro-refresh.yml` already:
- runs weekly (Mon 03:00 UTC) + manual `workflow_dispatch`,
- diffs the JSON,
- opens a **PR** (not a direct push) so a human eyeballs station counts before merge.

Keep this. The PR step is exactly the "review before it goes live" safety you want.
The backend serves the committed file from memory (`routers/metro.py`, `lru_cache`),
so **clients never touch Overpass** — matching your rate-limit concern. No CDN needed
until traffic grows; the committed file *is* the static asset.

---

## Part 4 — Immediate action (don't wait for the cron)

The weekly cron means the fix lands "eventually." To get an accurate map **now**:

1. Fix `refresh_metro.py` (§3.1–3.4).
2. Run it locally once: `python scripts/refresh_metro.py`.
3. Manually eyeball the diff — confirm 3 lines (Purple, Green, Yellow), sane counts:
   - Purple ≈ 37 operational stations (Challaghatta ↔ Whitefield/Kadugodi)
   - Green ≈ 30 operational stations (Madavara ↔ Silk Institute)
   - Yellow ≈ 16 stations (RV Road ↔ Bommasandra, opened Aug 2025 — should appear)
4. Commit the regenerated JSON. The renderer in `Zones.jsx` is line-agnostic, so
   Yellow shows up automatically.

> ⚠️ Sanity numbers above are approximate — **the validation gate (§3.4) + the PR
> diff are the real guardrails.** Do not trust my counts; trust the assertions and the
> visual diff.

---

## Part 5 — Open questions

1. **Direction dedup:** Namma Metro OSM relations are per-direction. Confirm the
   picking heuristic (forward relation only) doesn't drop a terminus. Needs one manual
   inspection of the actual Overpass response.
2. **`under_construction` / `planned` stations:** OSM tags these with
   `railway=construction` / `construction=subway`. Do we want to render them (dashed,
   greyed) per the original Problem 3 idea, or only operational? Recommend
   **operational-only** for v1 to avoid confusion.
3. **Path geometry (§3.3):** worth the extra parsing for curved lines, or are
   straight station-to-station segments good enough for v1? Recommend **defer** — ship
   correct ordering first, add curves later.
4. **Attribution:** ODbL requires "© OpenStreetMap contributors" somewhere on the map.
   Add to the Leaflet attribution control.

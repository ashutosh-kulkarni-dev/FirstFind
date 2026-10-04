# Location Search Upgrade — Execution Plan

**Status:** proposed (awaiting approval). No code changes until approved.
**Scope:** the location dimension of chatbot retrieval (`find_by_area` and the
area filter shared by every intent) + the two schema/seed changes it needs.

---

## The problem, precisely

"Shops in SG Palya" works; "shops in Tavrekere Road" returns nothing. The
instinct is that this is a *hierarchy* bug (Tavrekere Road is inside SG Palya).
It isn't. It's three separate defects in how location is modelled and matched.

1. **`area` is a single flat string doing three incompatible jobs** — display
   label, search key, and (absent) geographic containment. String equality
   (`Store.area == area`, `chatbot.py:251`) can never express "this road is
   inside that locality," no matter how good the fuzzy matcher gets.

2. **The searchable vocabulary is only the set of distinct `area` values.**
   `_known_areas()` returns `SELECT DISTINCT area` (`chatbot.py:101`), and
   `_extract_area()` can only resolve a query to one of those strings
   (`chatbot.py:107-132`). "SG Palya" is in that set (some store canonicalised
   to it); "Tavrekere Road" is not, so the query never even becomes a
   `find_by_area` intent — it silently degrades to `general_assistance`.
   It is not that the system filters Tavrekere Road out; the phrase does not
   exist in its dictionary.

3. **Coordinates exist but retrieval throws them away.** Every visible store has
   `lat/lng` (`models.py:27-28`); the chatbot never touches them. They feed only
   the map and zone clustering. So the one field that *does* encode containment
   and proximity is unused at search time.

Two supporting data-loss bugs make the proper fix impossible until fixed:

- **`locality_raw` is discarded at seed.** The messy source string (e.g.
  `"Tavrekere Road, SG Palya"`) is read only to derive `canonical_area`, then
  dropped (`seed.py:113`). The sub-locality text a token search would need is
  gone before it reaches the DB.
- **`geocode_precision` is dropped at seed.** The pipeline computes it
  (`build_dataset.py:162`, `"locality"` vs `None`) and writes it to
  `stores.json`, but there is no column for it (`models.py`) and `seed.py`
  ignores it. So at serving time you cannot tell a real Nominatim pin from an
  area-centroid backfill — which makes any distance ranking unsafe (see Risk 1).

---

## Reconciling with the locked retrieval principles

`CHATBOT_RETRIEVAL_PLAN.md` locks in: token-free/no-network retrieval,
hard-filter-then-rank, and **no silent substitution**. This plan keeps all
three. The key reframe:

> Proximity is not substitution. Today the "area filter" is *exact string
> equality on a flat label* — a broken definition of the constraint. Redefining
> it as "within the spatial/nominal extent of the queried place" is **correcting
> the filter**, not relaxing it. Stores outside that extent are still excluded;
> an empty extent still yields an honest empty answer.

And network stays out of the request path: query-geocoding is served from an
**offline gazetteer** built from the existing `geocode_cache.json` plus a small
curated locality file. Nominatim-at-request-time is an *optional*, cached,
default-off fallback only.

---

## Target design

Resolution runs in four offline, zero-token tiers. First tier that produces hits
wins its hits; tiers 2–3 union and co-rank.

```
query "shops in Tavrekere Road"
   │
   ├─ Tier 0  normalize the location phrase
   │
   ├─ Tier 1  EXACT/FUZZY canonical-area match      (existing path, kept)
   │            → hard area filter, as today
   │
   ├─ Tier 2  LOCALITY-STRING match                 (NEW, cheap, deterministic)
   │            substring/token match of the phrase against each store's
   │            locality_raw + area blob → direct hits
   │            (fixes the reported case whenever a store's raw text names
   │             the road/sub-locality)
   │
   ├─ Tier 3  SPATIAL match                          (NEW, uses coords you have)
   │            gazetteer: phrase → (lat,lng)[+bbox]; haversine radius over
   │            REAL-precision stores only → proximity hits
   │            (fixes general containment: parent⇄child with no shared token)
   │
   └─ rank: exact-area first, then ascending distance (real-precision),
            then the existing _relevance() score; honest empty if all tiers dry
```

Why both Tier 2 and Tier 3: Tier 2 is exact, deterministic, and needs no

geocoding — it nails "Tavrekere Road" the moment a store's `locality_raw`
contains it. Tier 3 handles the harder case where the child locality shares no
text token with the parent (query a road, get nearby stores that are only tagged
with the parent locality), and the symmetric case (query the parent, get stores
tagged only with the child road). You need both; neither alone covers it.

---

## The gazetteer (how spatial query-resolution stays offline)

`data/geocode_cache.json` already maps locality query strings →
`{lat,lng,matched}`. That is 90% of a gazetteer for free. Build step:

- **At seed time**, load the cache and emit `data/gazetteer.json`:
  `{ normalized_locality → {lat, lng, bbox?} }`, deduped/normalized.
- **Augment** with a small curated `data/localities_blr.json` (~150–250 major
  Bengaluru localities + coords, one-time asset) so common places a store isn't
  in still resolve.
- At request time, `_geocode_query(phrase)` is a dict lookup + fuzzy fallback
  over gazetteer keys. Zero network, sub-millisecond.
- **Optional** (config flag `QUERY_GEOCODE_ONLINE`, default `False`): on a
  gazetteer miss, one Nominatim call with a short timeout, result written back
  to the cache. Off by default to preserve the no-network principle.

Containment nuance: a point+fixed-radius is a crude circle. Nominatim already
returns a `boundingbox` per result — capture it so a broad locality
("Koramangala") uses point-in-bbox containment while a bare point uses radius.
Ship radius first (simple, tunable), add bbox as the refinement.

---

## File-by-file change list

| File | Change |
|---|---|
| `app/backend/app/models.py` | Add `locality_raw = Column(String(200))` and `geocode_precision = Column(String(20))` to `Store`. |
| `app/backend/app/seed.py` | Persist `locality_raw=row.get("locality_raw")` and `geocode_precision`; set `geocode_precision="centroid"` on the backfill branch (`seed.py:141-147`) so backfilled pins are distinguishable from real ones. |
| `app/backend/app/ml/geo.py` *(new)* | `build_gazetteer()` (seed-time, cache+curated → `gazetteer.json`); `geocode_query(phrase)` (offline lookup + fuzzy); `_within(store, center, radius/bbox)`. Reuses `utils.haversine_km` (already exists). |
| `app/backend/app/ml/chatbot.py` | Replace the single `Store.area == area` filter in `_rank()` with the 4-tier resolver. Broaden `_known_areas`/`_extract_area` to also index `locality_raw` tokens + gazetteer keys, so a sub-locality phrase resolves and `find_by_area` fires. Keep hard-filter-then-rank; add distance to the rank key. |
| `app/backend/app/config.py` | Add `LOCATION_RADIUS_KM = 2.0` (with per-place override hook) and `QUERY_GEOCODE_ONLINE = False`. Reuse existing `CITY_CENTER`. |
| `data/localities_blr.json` *(new)* | Curated locality→coord asset (one-time; can seed from OSM export). |
| `pipeline/build_dataset.py` | *(Phase 3, optional)* reverse-geocode each pin once → store admin ancestry (`suburb`, `city_district`) as `location_tags` for clean hierarchical filters. |

Note: this **does** change the schema, which `CHATBOT_RETRIEVAL_PLAN.md`
declared out of scope. That constraint belonged to that plan's scope; here the
two added columns are the root-cause fix and are justified. Called out
explicitly so it's a decision, not a drift.

---

## Execution phases (each independently shippable + verifiable)

1. **Persist the lost fields.** Add the two columns; wire `seed.py` to fill
   them (incl. `precision="centroid"` on backfill). Re-seed dev. Behaviour
   unchanged, but the data the fix needs now reaches the DB. *Lowest risk;
   ship first.*

2. **Tier 2 — locality-string match.** Persist-backed substring/token match on
   `locality_raw`. This alone resolves the reported "Tavrekere Road" case for
   every store whose raw text names the sub-locality. No geocoding, fully
   deterministic. *Highest value-per-effort; likely fixes the majority of
   reported misses.*

3. **Gazetteer + Tier 3 — spatial radius.** Build `gazetteer.json` at seed;
   `geocode_query`; radius filter over real-precision stores; distance in the
   rank key. Handles containment with no shared token. Guard on
   `geocode_precision` (Risk 1).

4. **Refinement (optional).** Bbox containment for broad localities; reverse-
   geocoded `location_tags` for explicit hierarchy filters in the UI; optional
   online geocode fallback behind the config flag.

Recommendation: **1 → 2 ships the fix the user actually reported.** 3 makes it
general. Do not start with 3.

---

## Verification (extend `app/backend/_verify.py`)

Token-free, SQLite, no network, no model download. New assertions:

- **Regression (the reported bug):** "shops in Tavrekere Road" returns a
  non-empty, correct set (the SG Palya / nearby stores). Fails on `main` today.
- **Symmetry:** querying a parent locality returns stores tagged only with a
  child road, and querying the child road returns stores tagged only with the
  parent. Both directions.
- **Precision guard:** a centroid-backfilled store never ranks by a false
  distance — it may match by string, but is excluded from radius ranking.
- **No-leak preserved:** proximity never returns a store outside the resolved
  radius/bbox; if nothing is within extent, the answer is honestly empty (not
  padded with city-wide stores).
- **Zero-network:** monkeypatch the network to raise; `respond()` still works
  (gazetteer path only). Proves retrieval stays offline by default.
- **Area-still-hard:** a clean "in <area>" query still returns strictly that
  area's stores, ordered — the existing contract is unbroken.

---

## Risks & mitigations

1. **Centroid pins poison distance ranking.** ~28 stores are backfilled to their
   area centroid (`seed.py:141-147`); ranking them by radius invents precision.
   *Mitigation:* Phase 1 tags them `precision="centroid"`; Tier 3 admits only
   `precision="locality"` into distance math. This is the single reason Phase 1
   must precede Phase 3.

2. **Production is Postgres/Supabase; `seed.py` does `drop_all`.** Re-seeding is
   fine in dev but destructive in prod. *Mitigation:* dev = re-seed; prod = a
   one-off `ALTER TABLE stores ADD COLUMN locality_raw …, geocode_precision …`
   + a backfill script that recomputes both from `stores.json`. No Alembic in
   the repo, so this is a hand-written migration — call it out in DEPLOYMENT.md.

3. **Gazetteer coverage gaps** for obscure sub-localities no store sits in and
   the curated file misses. *Mitigation:* Tier 2 (string match) covers most
   real queries without any geocoding; the optional online fallback (flag-gated)
   backstops the rest and self-populates the cache.

4. **Fixed radius is wrong for very large or very small localities.**
   *Mitigation:* bbox containment (Phase 4) when available; per-place radius
   override; tune the default against the `_verify` set, not by guessing.

5. **Scale.** Brute-force haversine over 131 stores is trivial. If this grows to
   thousands across cities, move `lat/lng` to a spatial index (PostGIS
   `geography` + `ST_DWithin`, or a geohash column). *Open question for you —
   see below.*

---

## Out of scope (deliberately)

- Embeddings / vector search for location (coordinates are the right tool).
- LLM-based query parsing (spends tokens in retrieval; violates principle 1).
- A hand-maintained alias table ("Tavrekere Road" → "SG Palya"). It feels like
  progress and then you maintain it forever — every new micro-locality is a new
  row. Coordinates + `locality_raw` scale; alias tables don't.

---

## One decision I need from you

Is 131 Bengaluru stores the target scale, or is this heading to thousands across
multiple cities? At 131, brute-force haversine in Python is correct and I'd not
add a spatial index. At multi-city scale, Phase 3 should write to a geohash /
PostGIS column from the start rather than being retrofitted. Your answer changes
Phase 3's storage, nothing earlier.

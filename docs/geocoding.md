# How the pipeline geocodes store data

Source: `pipeline/build_dataset.py` + `app/backend/app/seed.py`

---

## Overview

Geocoding converts each store's raw text locality (e.g. `"Koramanagala"`, `"8-th cross road, Madiwala new extension"`) into a `(lat, lng)` coordinate pair. It runs in two stages: the pipeline assigns coordinates where possible; the seeder backfills any that remain blank.

---

## Stage 1 — Pipeline (`pipeline/build_dataset.py`)

Runs once when you execute:

```
python pipeline/build_dataset.py
```

### Step 1 — Read the xlsx

```
Thrift Stores.xlsx  →  pandas DataFrame (131 rows)
```

Every row's `Location` cell is the raw input.

### Step 2 — Clean the locality string

`clean_locality(raw)` is called on each `Location` value before geocoding:

- Collapses multiple spaces into one.
- Strips leading/trailing commas.
- Applies a fixed correction table (`LOCALITY_FIXES`) for known misspellings:

  | Raw (case-insensitive match) | Corrected to |
  |---|---|
  | `koramanagala` | `Koramangala` |
  | `indra nagar` | `Indiranagar` |
  | `banglore` / `bangalore` | `Bengaluru` |
  | `whitefield` | `Whitefield` |

Output: a cleaned locality string like `"Koramangala"` or `"Madiwala new extension, Btm 1st stage"`.

### Step 3 — Check the geocode cache

Before making any network request, `geocode()` checks `data/geocode_cache.json`:

```
query string  →  cache hit?
                 ├─ YES → return cached (lat, lng) immediately, no request
                 └─ NO  → proceed to Nominatim
```

The cache key is the exact query string sent to Nominatim. On the first full run the cache is empty; on subsequent runs (e.g. after adding new stores to the xlsx) only genuinely new localities hit the network.

### Step 4 — Query Nominatim (OpenStreetMap)

If the cache misses, the pipeline sends an HTTPS request to the Nominatim geocoding API:

```
https://nominatim.openstreetmap.org/search
  ?q=<cleaned_locality>, Bengaluru, Karnataka
  &format=json
  &limit=1
  &countrycodes=in
```

- **Rate limit:** Nominatim's usage policy allows 1 request per second. The pipeline enforces this with a hard `sleep(1.1)` after every network call.
- **Timeout:** 15 seconds per request.
- **Result used:** first hit only (`results[0]`). The `display_name`, `lat`, and `lon` fields are extracted.

### Step 5 — Fallback query (chunk-based)

If the first query returns no results (e.g. the full address string is too specific for OSM to match), the pipeline retries with just the **last comma-delimited segment** of the cleaned locality:

```
"8-th cross road, Madiwala new extension"
  → retry with: "Madiwala new extension, Bengaluru, Karnataka"
```

This catches cases where a full street address fails but the neighbourhood name succeeds.

### Step 6 — Record the result

- **Hit:** store gets `lat`, `lng`, and `geocode_precision = "locality"`.
- **Miss (both attempts failed):** store gets `lat = null`, `lng = null`. A line is written to `data/FLAGS.md`:
  ```
  - GEOCODE FAILED: 'StoreName' at 'raw_locality' - pin manually
  ```

### Step 7 — Update the cache and write outputs

After all rows are processed:

- `data/geocode_cache.json` — updated with every new query result (hits and misses alike, so failed queries aren't retried on the next run).
- `data/stores.json` — 131 store records with coordinates where available.
- `data/stores.csv` — same data as a flat CSV.
- `data/FLAGS.md` — list of stores needing manual attention.

All files are written as **UTF-8** (explicit `encoding="utf-8"` on every write).

---

## Stage 2 — Seed backfill (`app/backend/app/seed.py`)

Runs when you execute:

```
python -m app.seed
```

The 28 stores that came out of the pipeline with `lat = null` are not left off the map — they are backfilled here before anything is written to the database.

### Step 8 — Compute area centroids

The seeder groups all stores that **do** have coordinates by their canonical area name, then computes the mean `(lat, lng)` for each group:

```python
area_pts = {}
for s in stores:
    if s.lat is not None:
        area_pts.setdefault(s.area, []).append((s.lat, s.lng))
```

### Step 9 — Fill blanks

For each store with `lat = null`:

```
same-area stores have coords?
  ├─ YES → assign mean(lat), mean(lng) of that area   ← locality-level precision
  └─ NO  → assign city centre (12.9716, 77.5946)      ← Bengaluru fallback
```

After this step every store in the database has a coordinate and appears on the map and is assignable to a zone.

---

## Current run summary (new dataset, 2026-08-15)

| Metric | Count |
|---|---|
| Total stores | 131 |
| Geocoded by Nominatim | 103 |
| Backfilled from area centroid | 28 |
| Cache entries after run | ~110 |
| Nominatim requests made | ~60 (new localities) |
| Approximate geocode time | ~70 s (1.1 s/req) |

---

## Re-running after xlsx changes

If you add rows to `Thrift Stores.xlsx` and rerun the pipeline:

1. Already-cached localities are free (instant, no network).
2. Only new locality strings hit Nominatim.
3. IDs (`blr-0001` … `blr-NNNN`) are assigned by row index — adding rows at the **end** keeps existing IDs stable. Inserting in the middle will renumber everything below the insertion point.
4. After the pipeline finishes, run `python -m app.seed` to drop, recreate, and repopulate the database from the updated `stores.json`.

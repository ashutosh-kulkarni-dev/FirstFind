# Store Ingestion Plan — `Thrift Stores.xlsx` → canonical dataset → DB

> Build the missing, **repeatable, non-destructive** front-of-pipeline stage that
> turns the human-maintained Excel master into the seed dataset the app runs on.

**Status:** planned 2026-08-31 · scope = store records only (reviews handled by
[`REVIEW_INGESTION_PLAN.md`](REVIEW_INGESTION_PLAN.md)).

---

## 1. Why this exists

- [`Thrift Stores.xlsx`](Thrift%20Stores.xlsx) (root) is the **raw master** a curator
  edits: `Name, Location, Insta ID, Timings, Special Mentions, Phone Number` — 131 rows.
- [`data/stores.json`](data/stores.json) / [`stores.csv`](data/stores.csv) are the
  **processed, geocoded** dataset [`seed.py`](app/backend/app/seed.py) loads. They were
  produced **once, by hand** — there is no script, so re-editing the Excel can't flow
  into the app reproducibly.
- This plan adds `scripts/ingest_stores.py`: Excel → normalized → geocoded → `stores.json`,
  idempotent and safe to re-run every time the curator updates the sheet.

## 1a. Merge strategy — decided after the first dry-run

The dry-run proved the current `stores.json` is **enriched beyond the Excel** (street-precise
geocodes, canonical localities, Instagram handles). A naive overwrite regressed **97 fields**,
mostly *losses* (27 stores would have lost their coordinates). So ingestion is **additive
merge**, never overwrite:

- **Existing store (matched by name):** an existing non-empty field WINS. The Excel only fills a
  **gap** (field currently empty/null). When both are non-empty and differ, keep the enriched
  value and **record a conflict for human review — do not apply it**.
- **New store (no match):** take the Excel row fully + cache-geocode.

Result on the current data: **13 additive gap-fills applied, 27 conflicts flagged (not applied),
0 coordinates lost.** This is the safe steady state.

## 2. Principles ("responsibly")

1. **Non-destructive.** Never blow away existing geocodes/IDs. Back up the current
   `stores.json`/`stores.csv` before writing; write only after validation passes.
2. **Idempotent & stable IDs.** Re-running on an unchanged sheet produces a byte-identical
   dataset. Existing stores keep their `blr-000N` id (matched by normalized name); genuinely
   new rows get the next free id. IDs never get reassigned.
3. **Preserve enrichment.** `lat/lng`, `geocode_precision`, and any `categories` already in
   `stores.json` are carried forward — the Excel doesn't have them and must not erase them.
4. **Geocode gently.** Resolve `Location` via the existing
   [`data/geocode_cache.json`](data/geocode_cache.json) first; only *new/unknown* localities
   hit Nominatim, rate-limited (1 req/s, descriptive User-Agent per its policy), and the
   result is written back to the cache. A run with no new localities makes **zero** network calls.
5. **Fail loud, change quiet.** Produce a validation report (row count, unmatched localities,
   missing coords, dropped rows). Abort the write on any hard error; leave the dataset untouched.

## 3. Transformations (Excel column → dataset field)

| Excel | → field | Rule |
|-------|---------|------|
| `Name` | `name` | trim; collapse internal whitespace |
| `Name` | `id` | match normalized name to existing `stores.json` id; else next `blr-XXXX` |
| `Location` | `locality_raw` | verbatim (kept for Tier-2 token search) |
| `Location` | `lat/lng`, `geocode_precision` | via `canonical_area()` + geocode cache; precision `locality`, else carry-forward, else `null` (hidden, no fake pin — matches seed policy) |
| `Insta ID` | `instagram` | strip `@`, URL prefixes, whitespace → handle or `null` |
| `Phone Number` | `phone` | normalize digits/`+91`; `null` if blank |
| `Timings` | `open_time`/`close_time` | parse `"11 AM - 7 PM"`, `"11.30 AM -8 PM"`, `"12-8 PM"` → 24h `HH:MM`; unparseable → `null` + keep raw in `timing_note` |
| `Special Mentions` | `notes`, `closed_days` | verbatim to `notes`; `"Closed on Mondays"` → `closed_days` (seed already does the note→closed_days step too) |

Reuses [`canonical_area()`](app/backend/app/seed.py#L52) so area normalization can't drift
between ingestion and seeding.

## 4. Deliverables

- `scripts/ingest_stores.py` — the ingester (stdlib + `openpyxl`; add `openpyxl` to
  `scripts` deps / `requirements.txt`).
  - `--dry-run` (default): read, transform, validate, print report + diff vs current
    `stores.json`. **Writes nothing.**
  - `--write`: after a clean dry-run, back up then write `stores.json` (+ regenerate
    `stores.csv`), preserving `version`/`city`, bumping `count`.
  - `--geocode-online`: allow Nominatim for unknown localities (default off → cache-only).
- Backup: `data/_archive/stores.json.<runtag>.bak` before any write.
- Short `scripts/README` note on the monthly/weekly curator workflow.

## 5. Validation (dry-run must show, before any write)

- rows in = rows out (131), minus explicitly-listed drops (blank name).
- every existing id preserved; list of new ids.
- localities: matched-from-cache vs need-geocode vs unresolved.
- stores that would end up with `null` coords (hidden) — must not silently grow.
- a unified field-level diff vs current `stores.json` so the curator sees exactly what changes.

## 6. How it fits the pipeline

New **Stage -1** in [`PIPELINE.md`](PIPELINE.md), upstream of seeding:

```
Thrift Stores.xlsx ─(ingest_stores.py)→ stores.json ─(seed.py)→ DB ─→ [reviews ingest → sentiment → score → zones → recs]
```

No change to `seed.py` or anything downstream — this just *feeds* the file seed already reads.

## 7. Relationship to the reviews plan (important find)

`data/_archive/googlemaps_reviews.csv` already contains **178 real Google Maps reviews for 45
stores** (`store_name, location, rating, review_text, date`). That is a **local, zero-API**
review source — it sidesteps the "API key must not hit limits" concern for the initial load.
Recommended sequencing:
1. **This plan** — get the store master ingested cleanly (stable ids + localities are the join key).
2. Then a small step in the reviews plan: load `googlemaps_reviews.csv`, match each review to a
   store id by (normalized name + area), run HF sentiment, recompute scores — no Google API call at all.
3. Google Places API stays the plan only for *ongoing weekly refresh* of new reviews.

## 8. Build order & self-review checklist

1. [x] `scripts/ingest_stores.py` skeleton: read Excel → list of raw dicts.
2. [x] Field transforms (timings parser handles `11 AM - 7 PM`, `11.30 AM -8 PM`, `12-8 PM`).
3. [x] Id matching + geocode-cache lookup + **additive merge** (carry-forward of enrichment).
4. [x] Validation report + diff; **dry-run prints, writes nothing**.
5. [x] Ran dry-run: 131 in / 131 out, **0 coords lost**, net diff = **13 additive gap-fills**,
       27 conflicts flagged (not applied). Merge strategy proven safe.
6. [x] `--write` path with **pristine, non-clobbering** backup (`data/_archive/stores.json.ingest.bak`); regenerate `stores.csv`.
7. [x] Add `scripts/requirements.txt` (`openpyxl`) + `scripts/README.md` curator workflow.
8. [x] **APPLIED** `--write`. Final state: 131/131 unique ids, idempotent (re-run = 0 changes),
       categories canonical (`womenswear`×5, `menswear`×5, `sportswear`×1).

### Two latent bugs the ingestion surfaced (and fixed)
- **Category text stored as raw categories.** The hand-made dataset kept `'Mens Clothing'`,
  `'Aesthetic Pieces'` etc. in `categories`. Now normalized to a controlled vocabulary
  (`menswear`/`womenswear`/`sportswear`); uncategorizable text dropped. Per your instruction.
- **Duplicate store IDs.** Naive name-matching collapsed the Excel's repeated names
  (`(Street)`, `Thrift Store`…) onto one id — 10 duplicate ids, which would break seeding
  (`id` is the PK). Fixed with **positional matching** (Excel and `stores.json` are perfectly
  row-aligned: 0/131 mismatches), guaranteeing unique ids.

## 9. Open questions

- On `--write`, also **re-run seeding** automatically (`python -m app.seed`, which drops+recreates
  tables), or leave seeding a separate manual step? (Recommend: keep separate — ingestion edits the
  file; seeding is the destructive DB step the operator runs deliberately.)
- Instagram/phone are almost entirely blank in the sheet — leave as-is (no enrichment) for now?

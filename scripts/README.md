# scripts/

Maintenance scripts. Install deps once: `pip install -r scripts/requirements.txt`.

## ingest_stores.py — Excel store master → dataset
Turns the human-maintained root file **`Thrift Stores.xlsx`** into the geocoded
dataset `seed.py` loads (`data/stores.json` + `data/stores.csv`). See
[`../STORE_INGESTION_PLAN.md`](../STORE_INGESTION_PLAN.md).

```bash
python scripts/ingest_stores.py                 # dry-run: report + diff, writes nothing
python scripts/ingest_stores.py --write         # back up (once), then write dataset
```

**Curator workflow (monthly / when the sheet changes):**
1. Edit `Thrift Stores.xlsx` (add stores, fill phone/instagram/hours).
2. `python scripts/ingest_stores.py` — review the dry-run report:
   - *Gap-fills* (empty fields filled from Excel) — applied.
   - *Conflicts* (Excel differs from an enriched value) — **kept enriched, not applied**; fix
     the Excel or the dataset by hand if the Excel is actually more correct.
   - *New stores* with null coords — add their locality to `data/geocode_cache.json` (or wire
     online geocoding) so they get a pin instead of being hidden.
3. `python scripts/ingest_stores.py --write` when the diff looks right.
4. Re-seed the DB deliberately: `cd app/backend && python -m app.seed` (DROPS + recreates tables).

**Safety properties:** additive merge (never overwrites enrichment), stable positional id
matching (unique ids, no collisions on duplicate names), idempotent (re-running an unchanged
sheet = 0 changes), pristine pre-ingest backup kept at
`data/_archive/stores.json.ingest.bak`.

## refresh_metro.py — Namma Metro stations from OSM
Run by `.github/workflows/metro-refresh.yml` weekly; opens a PR if data changed.

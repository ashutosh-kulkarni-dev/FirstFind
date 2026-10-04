"""Normalize Thrift Stores.xlsx into the canonical dataset (stores.csv + stores.json).

- Assigns stable IDs (blr-0001...) that must never change once published.
- Cleans locality names, parses timings where possible.
- Geocodes via Nominatim (OSM, free, 1 req/sec) at locality level.
- Flags rows needing manual attention (duplicates, non-Bengaluru, unparseable).

Usage: python pipeline/build_dataset.py [--skip-geocode]
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "Thrift Stores.xlsx"
OUT_DIR = ROOT / "data"
CACHE = OUT_DIR / "geocode_cache.json"

LOCALITY_FIXES = {
    "koramanagala": "Koramangala",
    "indra nagar": "Indiranagar",
    "banglore": "Bengaluru",
    "bangalore": "Bengaluru",
    "whitefield": "Whitefield",
}

def clean_locality(raw: str) -> str:
    s = re.sub(r"\s+", " ", str(raw)).strip().strip(",")
    low = s.lower()
    for bad, good in LOCALITY_FIXES.items():
        if bad in low:
            s = re.sub(re.escape(bad), good, s, flags=re.IGNORECASE)
            low = s.lower()
    return s

def parse_timings(raw):
    """Return (open, close, note) from free-text timings; None where unknown."""
    if not isinstance(raw, str) or not raw.strip():
        return None, None, None
    s = raw.strip()
    if re.search(r"24\s*hours", s, re.I):
        return "00:00", "23:59", "24 hours"
    m = re.match(r"opens?\s+(\d{1,2}(?::\d{2})?)\s*(am|pm)?", s, re.I)
    if m:
        return to_24h(m.group(1), m.group(2) or "am"), None, s
    m = re.match(
        r"(\d{1,2}(?:[.:]\d{2})?)\s*(am|pm)?\s*[-–to]+\s*(\d{1,2}(?:[.:]\d{2})?)\s*(am|pm)?",
        s, re.I,
    )
    if m:
        open_ap = m.group(2) or "am"
        close_ap = m.group(4) or "pm"
        return to_24h(m.group(1), open_ap), to_24h(m.group(3), close_ap), None
    return None, None, s

def normalize_category(s: str) -> str:
    """Tidy a free-text category label: collapse whitespace, Title Case.

    Merges casing variants ("Ladies Wear" / "Ladies wear") without inventing
    mappings between genuinely different labels ("Mens Clothing" vs "Mens
    Fashion" stay distinct — that's the real data).
    """
    return re.sub(r"\s+", " ", str(s).strip()).title()


def to_24h(t: str, ampm: str) -> str:
    t = t.replace(".", ":")
    h, _, mnt = t.partition(":")
    h = int(h)
    ampm = ampm.lower()
    if ampm == "pm" and h != 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mnt or '00'}"

def geocode(query: str, cache: dict) -> dict | None:
    if query in cache:
        return cache[query]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "countrycodes": "in"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "ThriftFind-MVP/0.1 (student capstone)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            results = json.load(r)
    except Exception as e:
        print(f"  geocode failed for {query!r}: {e}")
        return None
    hit = None
    if results:
        hit = {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"]),
               "matched": results[0]["display_name"]}
    cache[query] = hit
    time.sleep(1.1)  # Nominatim usage policy: max 1 req/sec
    return hit

def main():
    skip_geocode = "--skip-geocode" in sys.argv
    df = pd.read_excel(XLSX, sheet_name="Thrift Stores")
    OUT_DIR.mkdir(exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    stores, flags = [], []
    seen_names = {}
    for i, row in df.iterrows():
        name = str(row["Name"]).strip()
        raw_loc = clean_locality(row["Location"])
        insta = str(row["Insta ID"]).strip() if pd.notna(row["Insta ID"]) else None
        phone = re.sub(r"\D", "", str(row["Phone Number"])) if pd.notna(row["Phone Number"]) else None
        open_t, close_t, timing_note = parse_timings(row["Timings"] if pd.notna(row["Timings"]) else None)
        note = str(row["Special Mentions"]).strip() if pd.notna(row["Special Mentions"]) else None

        # The source "Timings" column is overloaded: some cells hold real hours,
        # others a stock/category label ("Mens Clothing", "Ladies Wear"). When
        # nothing parsed as a time, the cell is a category — not a timing note.
        categories = []
        if open_t is None and close_t is None and timing_note:
            categories.append(normalize_category(timing_note))
            timing_note = None

        key = name.lower()
        if key in seen_names:
            flags.append(f"DUPLICATE name: {name!r} (rows {seen_names[key]+1} and {i+1}) - merge manually")
        seen_names.setdefault(key, i)
        if re.search(r"churchgate|mumbai", raw_loc, re.I):
            flags.append(f"NOT BENGALURU?: {name!r} at {raw_loc!r} - verify or remove")

        store = {
            "id": f"blr-{i+1:04d}",
            "name": name,
            "locality_raw": raw_loc,
            "city": "Bengaluru",
            "instagram": insta,
            "phone": phone,
            "open_time": open_t,
            "close_time": close_t,
            "timing_note": timing_note,
            "notes": note,
            "lat": None,
            "lng": None,
            "geocode_precision": None,
            "stock_type": None,      # to fill: surplus | rejects | street | pre-owned
            "price_min": None,       # to fill via field visit / call
            "price_max": None,
            "categories": categories,  # real labels only, blank when not provided
            "verified_on": None,
        }
        if not skip_geocode:
            hit = geocode(f"{raw_loc}, Bengaluru, Karnataka", cache)
            if hit is None:
                # fall back to first comma-chunk (usually the locality)
                chunk = raw_loc.split(",")[-1].strip()
                hit = geocode(f"{chunk}, Bengaluru, Karnataka", cache)
            if hit:
                store.update(lat=hit["lat"], lng=hit["lng"], geocode_precision="locality")
            else:
                flags.append(f"GEOCODE FAILED: {name!r} at {raw_loc!r} - pin manually")
        stores.append(store)
        print(f"{store['id']}  {name:<32} {raw_loc[:45]:<47} "
              f"{'@'+insta if insta else '':<22} {'geo:ok' if store['lat'] else 'geo:--'}")

    # Always write UTF-8: stores.json/FLAGS.md keep non-ASCII names verbatim
    # (ensure_ascii=False), and Windows' default write_text encoding (cp1252)
    # would otherwise mangle them and break seed.py's utf-8 read.
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    pd.DataFrame(stores).to_csv(OUT_DIR / "stores.csv", index=False, encoding="utf-8")
    (OUT_DIR / "stores.json").write_text(json.dumps(
        {"version": 1, "city": "blr", "count": len(stores), "stores": stores},
        indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "FLAGS.md").write_text("# Rows needing manual attention\n\n" +
                                      "\n".join(f"- {f}" for f in flags) + "\n",
                                      encoding="utf-8")
    print(f"\nWrote {len(stores)} stores -> data/stores.csv, data/stores.json")
    print(f"{len(flags)} flags -> data/FLAGS.md")

if __name__ == "__main__":
    main()

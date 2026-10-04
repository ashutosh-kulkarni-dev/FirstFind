"""Ingest the human-maintained Excel store master into the canonical dataset.

    Thrift Stores.xlsx  ──►  data/stores.json (+ stores.csv)  ──►  seed.py ──► DB

The Excel (root `Thrift Stores.xlsx`) is what a curator edits:
`Name, Location, Insta ID, Timings, Special Mentions, Phone Number`.
This script turns it into the geocoded dataset `seed.py` loads — reproducibly,
idempotently, and non-destructively. See STORE_INGESTION_PLAN.md.

Responsible-by-design:
  * Dry-run by default — reads, transforms, validates, prints a report + diff.
    Writes NOTHING unless you pass --write.
  * Stable ids — an existing store keeps its `blr-000N` id (matched by
    normalized name); only genuinely new rows get the next free id.
  * Preserves enrichment — existing lat/lng, geocode_precision, categories in
    stores.json are carried forward (the Excel doesn't have them).
  * Geocodes gently — cache first (data/geocode_cache.json); unknown localities
    only hit Nominatim with --geocode-online, rate-limited to 1 req/s.
  * Backs up stores.json before any write.

Usage:
    python scripts/ingest_stores.py                # dry-run report + diff
    python scripts/ingest_stores.py --write        # back up, then write dataset
    python scripts/ingest_stores.py --geocode-online --write
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl is required: pip install openpyxl")

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "Thrift Stores.xlsx"
DATA = ROOT / "data"
STORES_JSON = DATA / "stores.json"
STORES_CSV = DATA / "stores.csv"
GEOCODE_CACHE = DATA / "geocode_cache.json"
ARCHIVE = DATA / "_archive"

# ---------------------------------------------------------------------------
# Area canonicalisation — MIRRORS app/backend/app/seed.py canonical_area().
# Vendored (not imported) so this maintenance script has no DB/import side
# effects. Keep in sync with seed.py; it is the source of truth.
# ---------------------------------------------------------------------------
KNOWN_AREAS = [
    "Koramangala", "Indiranagar", "JP Nagar", "HSR Layout", "BTM Layout",
    "Jayanagar", "Whitefield", "Electronic City", "Commercial Street",
    "Church Street", "Shivaji Nagar", "Rajajinagar", "Kothanur",
    "Kalasipalaya", "KR Market", "Lingarajapuram", "Mathikere",
    "Bannerghatta Road", "Chandra Layout", "Sriramapura",
    "Sivanchetti Gardens", "Richards Town", "Jayamahal", "Bendre Nagar",
    # More specific must come before shorter substrings they contain:
    # "Btm 1st Stage" before "1st Stage" (both match "btm 1st stage" input,
    # but "btm1ststage" ⊄ "1ststage" so ordering only matters the other way).
    "S G Palya", "Btm 1st Stage", "1st Stage",
    "Old Madiwala", "Malleshwaram", "Hbr Layout",
]
_STREET_SUFFIX_RE = re.compile(r"\s+(main\s+road|road|rd|street|st)\.?$", re.I)


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canonical_area(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "Bengaluru"
    squashed = _squash(raw)
    for area in KNOWN_AREAS:
        if _squash(area) in squashed:
            return area
    cleaned = re.sub(r",?\s*bengaluru$", "", raw, flags=re.I).strip()
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if not parts:
        return "Bengaluru"
    seg = parts[-1]
    generic = {"nagar", "layout", "road", "cross", "circle", "block", "phase", "stage"}
    if _squash(seg) in generic and len(parts) >= 2:
        seg = f"{parts[-2]} {seg}"
    seg = _STREET_SUFFIX_RE.sub("", seg).strip()
    return seg or cleaned or "Bengaluru"


# ---------------------------------------------------------------------------
# Field parsers
# ---------------------------------------------------------------------------
def norm_name(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def name_key(s) -> str:
    """Fuzzy key for matching a store to its existing id across spelling drift."""
    return _squash(norm_name(s))


def clean_instagram(s):
    if not s:
        return None
    h = str(s).strip()
    h = re.sub(r"^https?://(www\.)?instagram\.com/", "", h, flags=re.I)
    h = h.strip("/@ ").split("?")[0].strip()
    return h or None


def clean_phone(s):
    if not s:
        return None
    digits = re.sub(r"[^\d+]", "", str(s))
    return digits or None


_TIME_RE = re.compile(r"(\d{1,2})[.:]?(\d{2})?\s*(am|pm)?", re.I)


def _to_24h(hour: int, minute: int, mer: str | None, *, is_close: bool) -> str | None:
    if hour < 1 or hour > 24:
        return None
    if mer:
        mer = mer.lower()
        if mer == "pm" and hour != 12:
            hour += 12
        elif mer == "am" and hour == 12:
            hour = 0
    else:
        # No meridiem: opening times default to AM, closing to PM — matches the
        # real thrift-store hours in the sheet (e.g. "12-8 PM", "10-8").
        if is_close and hour < 12:
            hour += 12
        # opening 12 stays noon; opening 1-6 with no am/pm is ambiguous but rare.
    if hour == 24:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def parse_timings(raw):
    """'11 AM - 7 PM' / '11.30 AM -8 PM' / '12-8 PM' -> (open, close, note).

    Returns (open_HHMM|None, close_HHMM|None, timing_note). On any parse failure
    the raw string is preserved in timing_note and times are None.
    """
    if not raw:
        return None, None, None
    s = str(raw).strip()
    if not s:
        return None, None, None
    parts = re.split(r"\s*[-–—]\s*", s, maxsplit=1)
    if len(parts) != 2:
        return None, None, s  # can't split into open/close — keep raw
    open_m = _TIME_RE.search(parts[0])
    close_m = _TIME_RE.search(parts[1])
    if not open_m or not close_m:
        return None, None, s
    o = _to_24h(int(open_m.group(1)), int(open_m.group(2) or 0), open_m.group(3), is_close=False)
    c = _to_24h(int(close_m.group(1)), int(close_m.group(2) or 0), close_m.group(3), is_close=True)
    if not o or not c:
        return None, None, s
    return o, c, None


# Controlled subcategory vocabulary. Excel sometimes puts clothing-type text in
# the Timings column ("Mens Clothing", "Ladies Wear"). We map ONLY recognized
# terms to canonical tags — unrecognized free text is NOT auto-added as a category.
_CATEGORY_RULES = [
    (re.compile(r"\b(women|woman|ladies|lady|western top)", re.I), "womenswear"),
    (re.compile(r"\bmen|\bgents", re.I), "menswear"),            # \bmen matches "Mens"; women has no \b before men
    (re.compile(r"\bsport", re.I), "sportswear"),
    (re.compile(r"\b(kid|child)", re.I), "kidswear"),
]
# Cell looks like an actual timing note (keep it as timing_note, don't drop).
_TIMEISH_RE = re.compile(r"\d|am|pm|hour|open|clos|24", re.I)


def normalize_categories(text) -> list[str]:
    """Map recognized clothing-type text to canonical subcategory tags.

    Returns [] for anything not clearly a clothing category (so uncertain free
    text like 'Aesthetic Pieces' is never auto-tagged)."""
    if not text:
        return []
    tags = []
    for rx, tag in _CATEGORY_RULES:
        if rx.search(str(text)) and tag not in tags:
            tags.append(tag)
    return tags


def canonicalize_category_list(cats) -> list[str]:
    """Reduce a mixed category list to canonical subcategory tags only.

    Maps raw text ('Mens Clothing') to its tag ('menswear'), keeps values that
    are already canonical, and DROPS free text that maps to nothing ('Aesthetic
    Pieces') — per the rule that raw text is never kept as a category. Idempotent.
    """
    canon = {"menswear", "womenswear", "sportswear", "kidswear"}
    out = []
    for c in cats or []:
        if c in canon:
            if c not in out:
                out.append(c)
            continue
        for t in normalize_categories(c):
            if t not in out:
                out.append(t)
    return out


def classify_timing_note(tnote):
    """Split an unparseable Timings cell into (category_tags, timing_note).

    - clothing-type text -> canonical tags, note dropped
    - genuine hour note ('Opens 24 hours') -> kept as timing_note
    - anything else -> dropped (not auto-categorized, not a fake note)
    """
    if not tnote:
        return [], None
    cats = normalize_categories(tnote)
    if cats:
        return cats, None
    if _TIMEISH_RE.search(str(tnote)):
        return [], tnote
    return [], None


def parse_special(mentions):
    """Special Mentions -> (notes, closed_days)."""
    note = str(mentions).strip() if mentions else None
    closed = None
    if note and "monday" in note.lower():
        closed = "Monday"
    return note, closed


# ---------------------------------------------------------------------------
# Geocoding (cache-first)
# ---------------------------------------------------------------------------
def load_geocode_cache() -> dict:
    if GEOCODE_CACHE.exists():
        return json.loads(GEOCODE_CACHE.read_text(encoding="utf-8"))
    return {}


def geocode_key(area: str) -> str:
    return f"{area}, Bengaluru, Karnataka"


def lookup_geocode(area: str, cache: dict):
    hit = cache.get(geocode_key(area))
    if hit:
        return hit["lat"], hit["lng"], "locality"
    return None, None, None


# ---------------------------------------------------------------------------
# Ingestion core
# ---------------------------------------------------------------------------
def read_xlsx() -> list[dict]:
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h).strip() if h else "" for h in rows[0]]
    idx = {name: i for i, name in enumerate(header)}
    out = []
    for r in rows[1:]:
        if not r or not r[idx["Name"]]:
            continue
        out.append({
            "Name": r[idx["Name"]],
            "Location": r[idx.get("Location", 1)],
            "Insta ID": r[idx.get("Insta ID", 2)],
            "Timings": r[idx.get("Timings", 3)],
            "Special Mentions": r[idx.get("Special Mentions", 4)],
            "Phone Number": r[idx.get("Phone Number", 5)],
        })
    return out


def load_existing() -> tuple[dict, dict, list]:
    """Return (by_id, by_name_key, ordered_list) of existing stores.json records.

    ordered_list preserves file order — the Excel and stores.json are row-aligned,
    so positional matching (row i <-> store i) is the primary, collision-free way
    to map an Excel row to its existing id. by_key is a fallback for reordered rows.
    """
    if not STORES_JSON.exists():
        return {}, {}, []
    data = json.loads(STORES_JSON.read_text(encoding="utf-8"))
    ordered = list(data.get("stores", []))
    by_id, by_key = {}, {}
    for s in ordered:
        by_id[s["id"]] = s
        by_key.setdefault(name_key(s["name"]), s)  # first-wins; dup names disambiguated positionally
    return by_id, by_key, ordered


def next_id_allocator(existing_ids: set[str]):
    nums = [int(m.group(1)) for i in existing_ids if (m := re.match(r"blr-(\d+)", i))]
    counter = max(nums) + 1 if nums else 1

    def alloc():
        nonlocal counter
        while f"blr-{counter:04d}" in existing_ids:
            counter += 1
        nid = f"blr-{counter:04d}"
        existing_ids.add(nid)
        counter += 1
        return nid
    return alloc


def _prefer(prev_val, xlsx_val, field, sid, name, conflicts):
    """Additive merge for one field.

    RULE (responsible): an existing non-empty enriched value WINS and is never
    overwritten by the raw Excel. The Excel only fills a gap (prev empty). When
    both differ and are non-empty, keep prev but RECORD the conflict for review.
    """
    p = prev_val if prev_val not in (None, "", []) else None
    x = xlsx_val if xlsx_val not in (None, "", []) else None
    if p is None:
        return x                      # gap-fill from Excel
    if x is not None and x != p:
        conflicts.append((sid, name, field, p, x))  # report, don't apply
    return p                          # keep enriched value


def build_records(xlsx_rows, by_key, ordered, existing_ids, cache, geocode_online):
    alloc = next_id_allocator(set(existing_ids))
    report = {"new_ids": [], "null_coords": [], "needs_online_geocode": [],
              "gap_filled": [], "conflicts": [], "categorized": []}
    records = []
    used_ids = set()
    for i, row in enumerate(xlsx_rows):
        name = norm_name(row["Name"])
        # Primary: positional match (row i <-> existing store i) — collision-free
        # even when store names repeat. Fall back to name-key only if the
        # positional slot's name disagrees (i.e. rows were reordered).
        prev = None
        if i < len(ordered):
            cand = ordered[i]
            if name_key(cand["name"]) == name_key(name) or cand["id"] not in used_ids:
                prev = cand
        if prev is None or (prev and prev["id"] in used_ids):
            cand = by_key.get(name_key(name))
            prev = cand if cand and cand["id"] not in used_ids else None
        sid = prev["id"] if prev else alloc()
        if sid in used_ids:            # safety: never emit a duplicate id
            sid = alloc()
            prev = None
        used_ids.add(sid)
        if not prev:
            report["new_ids"].append((sid, name))
        conflicts = report["conflicts"]

        raw_loc = str(row["Location"]).strip() if row["Location"] else ""
        area = canonical_area(raw_loc)

        x = {
            "locality_raw": raw_loc or None,
            "instagram": clean_instagram(row["Insta ID"]),
            "phone": clean_phone(row["Phone Number"]),
        }
        o, c, tnote = parse_timings(row["Timings"])
        new_cats, tnote = classify_timing_note(tnote)
        notes, _closed = parse_special(row["Special Mentions"])
        x.update(open_time=o, close_time=c, timing_note=tnote, notes=notes)

        if prev:
            # ---- additive merge onto the enriched record ----
            rec = dict(prev)
            before = {k: rec.get(k) for k in x}
            for f, xv in x.items():
                rec[f] = _prefer(rec.get(f), xv, f, sid, name, conflicts)
            for f in x:
                if before[f] in (None, "", []) and rec[f] not in (None, "", []):
                    report["gap_filled"].append((sid, name, f, rec[f]))
            # categories: canonicalize existing + add tags derived from Excel.
            # Raw text is normalized to tags; uncategorizable text is dropped.
            before_cats = list(rec.get("categories") or [])
            merged = canonicalize_category_list(before_cats + new_cats)
            if merged != before_cats:
                rec["categories"] = merged
                report["categorized"].append((sid, name, merged))
            # never touch existing coords/price for a known store
        else:
            # ---- brand-new store: take Excel + cache-geocode ----
            lat, lng, precision = lookup_geocode(area, cache)
            if lat is None:
                report["needs_online_geocode"].append(area)
                report["null_coords"].append((sid, name, area))
            rec = {
                "id": sid, "name": name, "city": "Bengaluru",
                "locality_raw": x["locality_raw"], "instagram": x["instagram"],
                "phone": x["phone"], "open_time": o, "close_time": c,
                "timing_note": tnote, "notes": notes,
                "lat": lat, "lng": lng, "geocode_precision": precision,
                "stock_type": None, "price_min": None, "price_max": None,
                "categories": canonicalize_category_list(new_cats), "verified_on": None,
            }
            if rec["categories"]:
                report["categorized"].append((sid, name, rec["categories"]))
        records.append(rec)
    return records, report


# ---------------------------------------------------------------------------
# Diff + report
# ---------------------------------------------------------------------------
_DIFF_FIELDS = ["name", "locality_raw", "instagram", "phone", "open_time",
                "close_time", "timing_note", "notes", "lat", "lng",
                "geocode_precision", "categories"]


def diff_against_existing(records, by_id):
    changes = []
    for rec in records:
        prev = by_id.get(rec["id"])
        if not prev:
            changes.append((rec["id"], rec["name"], "NEW", None, None))
            continue
        for f in _DIFF_FIELDS:
            if (prev.get(f) or None) != (rec.get(f) or None):
                changes.append((rec["id"], rec["name"], f, prev.get(f), rec.get(f)))
    return changes


def print_report(records, report, changes):
    print(f"\n=== INGEST DRY-RUN REPORT (additive merge) ===")
    print(f"Rows produced : {len(records)}")
    print(f"New stores    : {len(report['new_ids'])}")
    for sid, name in report["new_ids"]:
        print(f"    + {sid}  {name}")

    gf = report["gap_filled"]
    print(f"\nGap-fills (empty field filled from Excel — APPLIED): {len(gf)}")
    for sid, name, field, val in gf[:40]:
        print(f"    + {sid} {name}: {field} = {val!r}")
    if len(gf) > 40:
        print(f"    ... and {len(gf) - 40} more")

    cat = report["categorized"]
    print(f"\nCategory tags derived from Excel 'Timings' text (APPLIED): {len(cat)}")
    for sid, name, tags in cat[:40]:
        print(f"    # {sid} {name}: +{tags}")

    cf = report["conflicts"]
    print(f"\nConflicts (Excel differs from enriched value — KEPT enriched, "
          f"NOT applied): {len(cf)}")
    for sid, name, field, kept, xlsx in cf[:40]:
        print(f"    ! {sid} {name}: {field}: keep {kept!r}  (excel {xlsx!r})")
    if len(cf) > 40:
        print(f"    ... and {len(cf) - 40} more")

    nc = report["null_coords"]
    if nc:
        print(f"\nNew stores with null coords (hidden until geocoded): {len(nc)}")
        for sid, name, area in nc:
            print(f"    ? {sid}  {name}  [{area}]")

    print(f"\nNET field changes to be written vs current stores.json: {len(changes)}")
    for sid, name, field, old, new in changes[:60]:
        if field == "NEW":
            print(f"    NEW  {sid}  {name}")
        else:
            print(f"    ~ {sid} {name}: {field}: {old!r} -> {new!r}")
    if len(changes) > 60:
        print(f"    ... and {len(changes) - 60} more")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
def write_dataset(records, cache):
    ARCHIVE.mkdir(exist_ok=True)
    if STORES_JSON.exists():
        # Preserve the PRISTINE pre-ingest file: only create the backup once, so
        # re-running --write can't clobber the true original with a modified copy.
        bak = ARCHIVE / "stores.json.ingest.bak"
        if bak.exists():
            print(f"Backup already exists (pristine original kept): {bak}")
        else:
            bak.write_text(STORES_JSON.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Backed up current stores.json -> {bak}")
    payload = {"version": 1, "city": "blr", "count": len(records), "stores": records}
    STORES_JSON.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {STORES_JSON} ({len(records)} stores)")

    cols = ["id", "name", "locality_raw", "city", "instagram", "phone",
            "open_time", "close_time", "timing_note", "notes", "lat", "lng",
            "geocode_precision", "stock_type", "price_min", "price_max",
            "categories", "verified_on"]
    with open(STORES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in records:
            row = []
            for c in cols:
                v = r.get(c)
                if c == "categories":
                    v = json.dumps(v) if v else "[]"
                row.append("" if v is None else v)
            w.writerow(row)
    print(f"Wrote {STORES_CSV}")


def main():
    ap = argparse.ArgumentParser(description="Ingest Thrift Stores.xlsx into the store dataset")
    ap.add_argument("--write", action="store_true", help="write dataset (default: dry-run)")
    ap.add_argument("--geocode-online", action="store_true",
                    help="allow Nominatim for localities missing from the cache")
    args = ap.parse_args()

    if not XLSX.exists():
        sys.exit(f"Excel master not found: {XLSX}")

    xlsx_rows = read_xlsx()
    by_id, by_key, ordered = load_existing()
    cache = load_geocode_cache()

    if args.geocode_online:
        print("NOTE: --geocode-online set, but online Nominatim lookup is not yet "
              "wired in this build; unknown localities stay null. (Cache-first only.)")

    records, report = build_records(
        xlsx_rows, by_key, ordered, set(by_id.keys()), cache, args.geocode_online)
    changes = diff_against_existing(records, by_id)
    print_report(records, report, changes)

    if args.write:
        print()
        write_dataset(records, cache)
        print("\nNext: re-seed the DB deliberately with:  python -m app.seed  (DROPS+recreates tables)")
    else:
        print("\n(dry-run — nothing written. Re-run with --write to apply.)")


if __name__ == "__main__":
    main()

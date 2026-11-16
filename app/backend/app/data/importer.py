"""Idempotent store importer: data/import/stores.csv -> the `stores` table.

Unlike `data/seed.py` (which DROPS every table, users included), this is safe to run
against a live database as often as you like:

  * Upsert by store id — new ids are inserted, existing ids are updated.
  * Fill-only by default — on an existing store only EMPTY fields are filled,
    so anything corrected by hand (e.g. a pin moved in the admin) is never
    overwritten. Pass --overwrite to let the CSV win.
  * Source-owned fields (store_type, Google rating / review count) always
    refresh, since the CSV is their only source.
  * Dry-run by default — prints the report and rolls back. Pass --write to commit.
  * Never deletes anything.

Run from app/backend:
    python -m app.data.importer                       # dry-run report
    python -m app.data.importer --write               # commit
    python -m app.data.importer --write --run-pipeline  # + zones / scores / recs
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import Counter
from pathlib import Path

from ..common.areas import KNOWN_AREAS, _squash, canonical_area
from ..common.geo import haversine_km
from ..config import ASSETS_DIR, REPO_ROOT
from ..database import Base, SessionLocal, engine, ensure_schema
from ..models import Store

log = logging.getLogger(__name__)

STORES_CSV = REPO_ROOT / "data" / "import" / "stores.csv"
HIDDEN_NAME = "hidden_stores.csv"

STORE_TYPES = {"thrift", "retail_fashion", "branded"}

# The scraped rows carry one of two generic price bands per store type rather
# than a real per-store price. They are imported but flagged as estimates.
PLACEHOLDER_PRICE_BANDS = {(300, 1500), (500, 3500)}

# Fields the CSV is the only source for — refreshed on every import.
ALWAYS_REFRESH = {"store_type", "google_rating", "google_review_count"}


# ---------------------------------------------------------------------------
# Field cleaning (pure functions — unit tested)
# ---------------------------------------------------------------------------

_HHMM_RE = re.compile(r"(\d{1,2}):(\d{2})")
_AMPM_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\b", re.I)


def clean_time(raw: str | None) -> str | None:
    """Normalise '10:00 AM', '9:30 PM', '10 PM', '20:00' to 24h 'HH:MM'."""
    s = (raw or "").replace(" ", " ").replace("\xa0", " ").strip()
    if not s:
        return None
    m = _AMPM_RE.search(s)
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0)
        minute = int(m.group(2) or 0)
    else:
        m = _HHMM_RE.fullmatch(s)
        if not m:
            return None
        hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return f"{hour:02d}:{minute:02d}"


# Google Maps "live status" strings captured at scrape time. They go stale
# within hours, so they are mined for a closing time and then dropped.
_STATUS_NOTE_RE = re.compile(r"^(closes|opens|reopens|open now)\b", re.I)
_CLOSED_FOR_GOOD_RE = re.compile(r"permanently closed", re.I)


def clean_hours(open_raw, close_raw, note_raw):
    """Return (open_time, close_time, timing_note, permanently_closed)."""
    note = (note_raw or "").replace(" ", " ").strip()
    open_time, close_time = clean_time(open_raw), clean_time(close_raw)
    if close_time is None and note.lower().startswith("closes"):
        close_time = clean_time(note)
    # Midnight opening = unknown/placeholder in this dataset (same rule as
    # data/seed.py) — drop both so "open now" is never falsely true.
    if open_time == "00:00":
        open_time = close_time = None
    permanently_closed = bool(_CLOSED_FOR_GOOD_RE.search(note))
    if _STATUS_NOTE_RE.match(note):
        note = ""
    return open_time, close_time, (note or None), permanently_closed


# A real category is a short label such as "Clothing store" or "menswear".
# The scrape also leaked street addresses and marketing blurbs into this
# column; those are rejected.
_CATEGORY_OK_RE = re.compile(
    r"(store|shop|boutique|mall|tailor|wear|manufacturer)$", re.I)


def clean_categories(raw: str | None) -> list[str]:
    """Parse a Python-list-looking string into clean category labels.

    Not ast.literal_eval: values like ['Women's clothing store'] contain an
    unescaped apostrophe and are not valid Python.
    """
    s = (raw or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    out: list[str] = []
    for part in re.split(r"""['"]\s*,\s*['"]""", s):
        c = part.strip().strip("'\"").strip()
        if not c or len(c) > 40 or "," in c or re.search(r"\d", c):
            continue
        if c.isupper() or "&" in c or " for " in c or not _CATEGORY_OK_RE.search(c):
            continue
        c = c[0].upper() + c[1:]
        if c not in out:
            out.append(c)
    return out


_ADDRESSY_RE = re.compile(
    r"\d|\b(shop|store) no\b|\bfloor\b|\brd\b|\broad\b|\bstreet\b|\bnear\b|\bopp\b|\bmall\b",
    re.I)
_BLURB_HINT_RE = re.compile(r"&| for | with | of ", re.I)


def blurb_from_categories(raw: str | None) -> str | None:
    """Google's one-line editorial description, when the scrape captured it in
    the categories column (e.g. "Stalwart for iconic jeans & casualwear")."""
    s = (raw or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    for part in re.split(r"""['"]\s*,\s*['"]""", s):
        c = part.strip().strip("'\"").strip()
        if 15 <= len(c) <= 90 and _BLURB_HINT_RE.search(c) and not _ADDRESSY_RE.search(c):
            return c[0].upper() + c[1:] + ("" if c.endswith(".") else ".")
    return None


def clean_phone(raw: str | None) -> str | None:
    s = (raw or "").strip()
    s = re.sub(r"\.0$", "", s)          # spreadsheet float artefact
    return s[:30] or None


def clean_notes(raw: str | None) -> str | None:
    s = (raw or "").strip()
    if s.lower().startswith("scraped from google maps"):
        return None                     # provenance boilerplate, not a user note
    return s[:500] or None


# Localities the scraped Google addresses use that seed.KNOWN_AREAS (built for
# the original thrift list) doesn't cover.
EXTRA_AREAS = [
    "Marathahalli", "Kammanahalli", "Basavanagudi", "Banashankari", "Yelahanka",
    "Hebbal", "RT Nagar", "Bellandur", "Sarjapur Road", "Chickpet", "Brigade Road",
    "MG Road", "Frazer Town", "Kalyan Nagar", "Basaveshwar Nagar", "Vijayanagar",
    "Yeshwanthpur", "Konanakunte", "Ulsoor", "Domlur", "KR Puram", "Mahadevapura",
    "Hennur", "Banaswadi", "Shanti Nagar", "Ashok Nagar", "Richmond Town",
    "Gandhi Nagar", "Nagarbhavi", "Kengeri", "Rajarajeshwari Nagar", "Uttarahalli",
    "Bommanahalli", "Begur", "Hulimavu", "Arekere", "Wilson Garden", "Cox Town",
    "Sadashivanagar", "Sanjay Nagar", "Vasanth Nagar", "Seshadripuram",
    "Kumaraswamy Layout", "Padmanabhanagar", "Jalahalli", "Vidyaranyapura",
    "Thanisandra", "Hoodi", "Brookefield", "Kadugodi", "Varthur", "Kundalahalli",
    "CV Raman Nagar", "Ramamurthy Nagar", "Peenya", "Majestic",
]
# "1st Stage" is too generic to match inside a full street address.
_ADDRESS_AREAS = [a for a in KNOWN_AREAS if a != "1st Stage"] + EXTRA_AREAS
_ALIASES = {"brigaderd": "Brigade Road", "mahatmagandhird": "MG Road",
            "mahatmagandhiroad": "MG Road", "churchst": "Church Street",
            "jpnagar": "JP Nagar", "hsr": "HSR Layout", "btm": "BTM Layout",
            "chikpet": "Chickpet", "ramamurthinagar": "Ramamurthy Nagar",
            "malleswaram": "Malleshwaram"}
_CITY_RE = re.compile(r"^(bengaluru|bangalore)$", re.I)


def _known_area(text: str) -> str | None:
    sq = _squash(text)
    if not sq:
        return None
    for area in _ADDRESS_AREAS:
        if _squash(area) in sq:
            return area
    for alias, area in _ALIASES.items():
        if alias in sq:
            return area
    return None


def looks_like_phone(text: str | None) -> bool:
    return bool(re.fullmatch(r"[\d\s+()-]{8,}", (text or "").strip()))


_JUNK_AREA_RE = re.compile(
    r"^(near|nearby|next|opp|opposite|shop|store|upper|lower|ground|road|flyover|"
    r"rest house|\d+(st|nd|rd|th)?\b)|[\d|+]|floor", re.I)


def _is_junk_area(area: str) -> bool:
    """True for values that are not a neighbourhood: '114', 'Ground Floor',
    a plus-code, 'Shop No', 'nearby Starbucks', or just the city name."""
    a = (area or "").strip()
    return len(a) < 4 or bool(_CITY_RE.match(a)) or bool(_JUNK_AREA_RE.search(a))


NEAREST_PLACE_MAX_KM = 3.0
_PLACES_JSON = ASSETS_DIR / "bengaluru_places.json"
_places_cache: list | None = None


def nearest_place(lat: float, lng: float) -> str | None:
    """Name of the closest well-known Bengaluru locality within
    NEAREST_PLACE_MAX_KM, from the repo's gazetteer; None if nothing is close."""
    global _places_cache
    if _places_cache is None:
        try:
            _places_cache = json.loads(_PLACES_JSON.read_text(encoding="utf-8"))
        except OSError:
            _places_cache = []
    best, best_km = None, NEAREST_PLACE_MAX_KM
    for place in _places_cache:
        km = haversine_km(lat, lng, place["lat"], place["lng"])
        if km <= best_km:
            best, best_km = place["canonical"], km
    # Normalise spelling to the app's canonical names ("Malleswaram" -> "Malleshwaram").
    return (_known_area(best) or best) if best else None


def derive_area(locality: str, address: str | None,
                lat: float | None = None, lng: float | None = None) -> str:
    """Best neighbourhood name for a store.

    1. A known locality named in `locality_raw` (common/areas.py's rule).
    2. Else read it from the street address: Google formats these as
       "..., <locality>, Bengaluru, Karnataka 5600xx", so walk the segments
       before the city backwards and take the first known locality, falling
       back to the segment right before the city.
    3. Else seed.canonical_area(locality).
    4. If that is still not a real neighbourhood ("114", "Ground Floor", just
       "Bengaluru") and the store has a pin, use the nearest well-known
       locality to the pin. Last resort: "Bengaluru".
    """
    area = canonical_area(locality)
    if area in KNOWN_AREAS:
        return area
    segs = [p.strip() for p in (address or "").split(",") if p.strip()]
    city_at = next((i for i, p in enumerate(segs) if _CITY_RE.match(p)), None)
    if city_at:
        before = segs[:city_at]
        for seg in reversed(before):
            known = _known_area(seg)
            if known:
                return known
        if not _is_junk_area(before[-1]) and len(before[-1]) <= 40:
            return before[-1]
    known = _known_area(locality)
    if known:
        return known
    if not _is_junk_area(area):
        return area
    if lat is not None and lng is not None:
        return nearest_place(lat, lng) or "Bengaluru"
    return "Bengaluru"


def _num(raw, cast):
    try:
        return cast(float(raw))
    except (TypeError, ValueError):
        return None


def clean_row(row: dict) -> dict:
    """Turn one CSV row into a dict of Store column values."""
    locality = (row.get("locality_raw") or "").strip()
    open_time, close_time, timing_note, closed_for_good = clean_hours(
        row.get("open_time"), row.get("close_time"), row.get("timing_note"))

    lat, lng = _num(row.get("lat"), float), _num(row.get("lng"), float)
    if lat is None or lng is None:
        lat = lng = None
    precision = (row.get("geocode_precision") or "").strip() or None

    price_min, price_max = _num(row.get("price_min"), int), _num(row.get("price_max"), int)
    notes = clean_notes(row.get("notes"))
    closed_days = "Monday" if "monday" in f"{notes or ''} {timing_note or ''}".lower() else ""

    store_type = (row.get("store_type") or "").strip() or "thrift"
    if store_type not in STORE_TYPES:
        store_type = "thrift"

    # Google's description: its own column (verified candidates), else the
    # editorial line the scrape left in the categories column.
    description = ((row.get("description") or "").strip()
                   or blurb_from_categories(row.get("categories")))

    # Some scraped rows have the phone number in the address column.
    address = (row.get("address") or "").strip() or None
    phone = clean_phone(row.get("phone"))
    if looks_like_phone(address):
        phone, address = phone or clean_phone(address), None

    return {
        "id": row["id"].strip(),
        "name": row["name"].strip()[:200],
        "area": derive_area(locality, address, lat, lng)[:100],
        "city": (row.get("city") or "Bengaluru").strip(),
        "lat": lat, "lng": lng,
        "geocode_precision": precision if lat is not None else None,
        "open_time": open_time, "close_time": close_time,
        "timing_note": timing_note,
        "notes": notes,
        "phone": phone,
        "instagram": (row.get("instagram") or "").strip()[:120] or None,
        "categories": ",".join(clean_categories(row.get("categories")))[:300],
        "closed_days": closed_days,
        "price_min": price_min, "price_max": price_max,
        "price_estimated": (price_min, price_max) in PLACEHOLDER_PRICE_BANDS,
        "locality_raw": locality[:200] or None,
        "store_type": store_type,
        "address": address[:300] if address else None,
        # Optional columns (present for stores promoted by verify_candidates).
        "google_place_id": (row.get("google_place_id") or "").strip()[:120] or None,
        "description": description,
        "description_source": "google" if description else None,
        "google_rating": _num(row.get("rating"), float),
        "google_review_count": _num(row.get("review_count"), int),
        "is_active": not closed_for_good,
    }


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def _is_empty(v) -> bool:
    return v is None or v == ""


def load_hidden(stores_csv: Path) -> set[str]:
    """Ids listed in hidden_stores.csv (next to the stores file): places that
    turned out not to be clothing stores. They stay in the data but are
    switched off, so they never show on the site."""
    path = Path(stores_csv).parent / HIDDEN_NAME
    if not path.exists():
        return set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {(r.get("id") or "").strip() for r in csv.DictReader(f)} - {""}


def import_stores(db, csv_path: Path | None = None, overwrite: bool = False) -> dict:
    """Upsert every row of csv_path. Flushes but does not commit."""
    csv_path = csv_path or STORES_CSV   # resolved at call time, not import time
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    hidden = load_hidden(csv_path)

    existing = {s.id: s for s in db.query(Store).all()}
    created = updated = unchanged = 0
    seen_ids: set[str] = set()
    no_coords: list[tuple[str, str]] = []
    inactive: list[tuple[str, str]] = []
    types: Counter = Counter()

    for row in rows:
        if not (row.get("id") or "").strip() or not (row.get("name") or "").strip():
            continue
        vals = clean_row(row)
        sid = vals["id"]
        if sid in hidden:
            vals["is_active"] = False
        if sid in seen_ids:
            log.warning("Duplicate id %s in CSV — later row ignored", sid)
            continue
        seen_ids.add(sid)
        types[vals["store_type"]] += 1

        store = existing.get(sid)
        if store is None:
            db.add(Store(experience_score=None, review_count=0, **vals))
            created += 1
            final_lat, final_active = vals["lat"], vals["is_active"]
        else:
            changed = False
            for field, new in vals.items():
                if field in ("id", "lat", "lng", "geocode_precision"):
                    continue
                cur = getattr(store, field)
                if field in ALWAYS_REFRESH:
                    apply = new is not None and new != cur
                elif field == "is_active":
                    # Only ever switch a store OFF from the CSV; re-activating
                    # is a deliberate admin action.
                    apply = new is False and cur is not False
                elif overwrite:
                    apply = not _is_empty(new) and new != cur
                else:
                    apply = _is_empty(cur) and not _is_empty(new)
                if apply:
                    setattr(store, field, new)
                    changed = True
            # Coordinates move as one unit (lat, lng, precision) so a pin is
            # never half-replaced.
            has_pin = store.lat is not None and store.lng is not None
            if vals["lat"] is not None and (overwrite or not has_pin):
                pin = (vals["lat"], vals["lng"], vals["geocode_precision"])
                if pin != (store.lat, store.lng, store.geocode_precision):
                    store.lat, store.lng, store.geocode_precision = pin
                    changed = True
            updated += changed
            unchanged += not changed
            final_lat, final_active = store.lat, store.is_active

        if final_lat is None:
            no_coords.append((sid, vals["name"]))
        if final_active is False:
            inactive.append((sid, vals["name"]))

    db.flush()
    return {
        "rows": len(rows), "created": created, "updated": updated,
        "unchanged": unchanged, "by_type": dict(types),
        "no_coords": no_coords, "inactive": inactive,
        "total_in_db": db.query(Store).count(),
    }


def prune_stores(db, csv_path: Path | None = None, max_share: float = 0.25) -> dict:
    """Delete every store that is NOT in the stores CSV, with everything that
    hangs off it (reviews, saves, views, recommendations). Flushes, no commit.

    Deliberate, destructive and never part of a normal run. Refuses to act if
    it would remove more than max_share of the stores — that means the CSV is
    wrong, not the database."""
    from ..models import Interaction, Review, SavedListItem, StoreSimilarity, UserRecommendation
    csv_path = csv_path or STORES_CSV
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        keep = {(r.get("id") or "").strip() for r in csv.DictReader(f)} - {""}
    all_ids = [sid for (sid,) in db.query(Store.id)]
    gone = sorted(set(all_ids) - keep)
    if not gone:
        return {"stores_removed": 0, "reviews_removed": 0, "ids": []}
    if not keep or len(gone) > max_share * len(all_ids):
        raise RuntimeError(f"Refusing to prune {len(gone)} of {len(all_ids)} stores "
                           f"(CSV has {len(keep)} ids) — check {csv_path}")
    reviews = db.query(Review).filter(Review.store_id.in_(gone)).delete(synchronize_session=False)
    for model, cols in ((Interaction, ("store_id",)), (SavedListItem, ("store_id",)),
                        (UserRecommendation, ("store_id",)),
                        (StoreSimilarity, ("store_id", "similar_id"))):
        for col in cols:
            db.query(model).filter(getattr(model, col).in_(gone)).delete(synchronize_session=False)
    db.query(Store).filter(Store.id.in_(gone)).delete(synchronize_session=False)
    db.flush()
    log.info("Pruned %d stores not in %s (and %d of their reviews)",
             len(gone), csv_path.name, reviews)
    return {"stores_removed": len(gone), "reviews_removed": reviews, "ids": gone}


def print_report(r: dict, wrote: bool) -> None:
    print(f"Stores CSV rows: {r['rows']}  |  created {r['created']}  "
          f"updated {r['updated']}  unchanged {r['unchanged']}")
    print(f"By type: {r['by_type']}")
    print(f"Stores in DB after import: {r['total_in_db']}")
    print(f"Hidden — no coordinates ({len(r['no_coords'])}), need a manual pin:")
    for sid, name in r["no_coords"]:
        print(f"    {sid}  {name}")
    print(f"Hidden — marked permanently closed ({len(r['inactive'])}):")
    for sid, name in r["inactive"]:
        print(f"    {sid}  {name}")
    print("COMMITTED." if wrote else "DRY RUN — nothing written. Re-run with --write to commit.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Idempotently import stores from CSV")
    ap.add_argument("--csv", type=Path, default=STORES_CSV)
    ap.add_argument("--write", action="store_true", help="commit (default is a dry run)")
    ap.add_argument("--overwrite", action="store_true",
                    help="let CSV values replace existing non-empty DB values")
    ap.add_argument("--run-pipeline", action="store_true",
                    help="after a --write, recompute zones, scores and recommendations")
    args = ap.parse_args()

    # Make sure the tables and the newer columns exist before touching rows
    # (the web app does the same on boot; this lets the importer run first).
    Base.metadata.create_all(engine)
    ensure_schema()

    db = SessionLocal()
    try:
        report = import_stores(db, args.csv, overwrite=args.overwrite)
        if args.write:
            db.commit()
        else:
            db.rollback()
        print_report(report, args.write)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if args.write and args.run_pipeline:
        from ..jobs.pipeline import run_pipeline
        print("Running ML pipeline...")
        print(run_pipeline())


if __name__ == "__main__":
    main()

"""Verify candidate stores against Google, then promote the confirmed ones.

    data/import/candidates_osm.csv   (candidate stores, unverified)
        --verify-->  each row checked with one Google Places Text Search call
        --promote--> confirmed rows appended to data/import/stores.csv
                     (+ any reviews Google returned to data/import/reviews.csv)

A candidate is VERIFIED only if Google returns a place that
  * sits within MAX_MATCH_KM of the candidate's map pin (when it has one),
  * has a matching name (or the candidate's brand in its name), and
  * is marked OPERATIONAL.
Otherwise it is recorded as `closed`, `not_found` or `duplicate` and is never
promoted. For `not_found` the closest thing Google did return is kept in the
`near_miss` column so a person can judge it.

To add a store yourself, append a candidate and let the daily job verify it:
    python -m app.verify_candidates --add "Store Name" --area "Indiranagar" --type thrift

These calls count against the Google key's quota. Nothing is sent without
--verify, each run is capped by --limit, and progress is saved after every row
so a run can be stopped and resumed. Rows already checked are never re-sent.

Run from app/backend (needs GOOGLE_PLACES_API_KEY with "Places API (New)" enabled):
    python -m app.verify_candidates                  # status report, no API calls
    python -m app.verify_candidates --verify --limit 90
    python -m app.verify_candidates --promote        # dry run: what would be added
    python -m app.verify_candidates --promote --write
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import Counter
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from .config import CITY_CENTER, REPO_ROOT
from .utils import haversine_km

log = logging.getLogger(__name__)

IMPORT_DIR = REPO_ROOT / "data" / "import"
CANDIDATES_CSV = IMPORT_DIR / "candidates_osm.csv"
CANDIDATE_REVIEWS_JSON = IMPORT_DIR / "candidates_reviews.json"
STORES_CSV = IMPORT_DIR / "stores.csv"
REVIEWS_CSV = IMPORT_DIR / "reviews.csv"

MAX_MATCH_KM = 0.3          # Google's pin must be this close to the candidate's
MIN_NAME_SIMILARITY = 0.75
DUPLICATE_KM = 0.15         # same name this close to an existing store = duplicate
CITY_RADIUS_M = 25_000      # search area for a candidate that has no pin

SEARCH_FIELDS = ",".join("places." + f for f in (
    "id", "displayName", "formattedAddress", "location", "businessStatus",
    "rating", "userRatingCount", "editorialSummary", "primaryTypeDisplayName",
    "nationalPhoneNumber", "reviews"))

BASE_COLS = ["osm_id", "name", "brand", "store_type", "locality_raw", "address", "lat", "lng",
             "open_time", "close_time", "opening_hours_raw", "phone", "website",
             "categories", "osm_last_edit"]
# Columns this tool adds to the candidates file.
RESULT_COLS = ["verified", "place_id", "google_name", "google_address", "google_lat",
               "google_lng", "google_rating", "google_review_count", "description",
               "google_type", "google_phone", "match_km", "near_miss", "checked_on",
               "promoted_id"]


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Words too common in shop names to prove two names are the same shop:
# "Preethi Textiles" and "Gupta's Textiles" share only the generic part.
_GENERIC_WORDS = {
    "textile", "textiles", "fashion", "fashions", "collection", "collections",
    "garment", "garments", "boutique", "store", "stores", "shop", "showroom",
    "wear", "wears", "clothing", "clothes", "creations", "designs", "designer",
    "silk", "silks", "sarees", "saree", "mens", "men", "ladies", "women", "womens",
    "kids", "the", "and", "of", "by", "bengaluru", "bangalore", "india",
    "factory", "outlet", "exclusive", "brand", "pvt", "ltd",
    "sri", "shri", "shree", "sree", "new", "export", "exports", "enterprises",
}


def _distinctive(name: str) -> str:
    """The name minus generic shop words, squashed ('Preethi Textiles' -> 'preethi')."""
    words = re.findall(r"[a-z0-9]+", (name or "").lower().replace("'s", ""))
    return "".join(w for w in words if w not in _GENERIC_WORDS)


def name_similarity(a: str, b: str) -> float:
    """0..1 on the distinctive part of two shop names — tolerant of suffixes
    like '- Indiranagar, Bengaluru' and of typos, but not fooled by shared
    generic words."""
    x, y = _distinctive(a), _distinctive(b)
    if not x or not y:                       # nothing distinctive: compare whole names, strictly
        x, y = _squash(a), _squash(b)
        return 1.0 if x and x == y else 0.0
    if min(len(x), len(y)) >= 4 and (x in y or y in x):
        return 1.0
    return SequenceMatcher(None, x, y).ratio()


def _has_pin(cand: dict) -> bool:
    return bool(str(cand.get("lat") or "").strip() and str(cand.get("lng") or "").strip())


def pick_match(cand: dict, places: list[dict]) -> tuple[str, dict | None, float | None, str]:
    """Decide a candidate's status from Google's results.

    Returns (status, place, distance_km, near_miss) where status is
    'verified' | 'closed' | 'not_found'. `near_miss` describes the best result
    that was rejected (empty when something matched or Google returned nothing).
    A candidate without a pin is matched on name alone, taking Google's first hit.
    """
    pinned = _has_pin(cand)
    if pinned:
        lat, lng = float(cand["lat"]), float(cand["lng"])
    best, best_km = None, None
    miss, miss_rank = "", None
    for p in places:
        loc = p.get("location") or {}
        if "latitude" not in loc:
            continue
        gname = (p.get("displayName") or {}).get("text", "")
        km = haversine_km(lat, lng, loc["latitude"], loc["longitude"]) if pinned else None
        sim = max(name_similarity(cand["name"], gname),
                  name_similarity(cand.get("brand", ""), gname) if cand.get("brand") else 0.0)
        name_ok = sim >= MIN_NAME_SIMILARITY
        near_ok = km is None or km <= MAX_MATCH_KM
        if name_ok and near_ok:
            if best is None or (km is not None and km < best_km):
                best, best_km = p, km
            if not pinned:
                break                          # Google's ranking decides
            continue
        # Remember the most plausible reject: right name first, then nearest.
        rank = (0 if name_ok else 1, km if km is not None else 0)
        if miss_rank is None or rank < miss_rank:
            why = "too far" if name_ok else "name differs"
            where = f"{km * 1000:.0f} m away" if km is not None else "no pin to compare"
            miss, miss_rank = f"{gname} ({where}; {why})", rank
    if best is None:
        return "not_found", None, None, miss
    status = best.get("businessStatus", "OPERATIONAL")
    km_out = round(best_km, 3) if best_km is not None else None
    return ("verified" if status == "OPERATIONAL" else "closed"), best, km_out, ""


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> tuple[list[dict], list[str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    tmp.replace(path)          # atomic: never leaves a half-written file


def load_candidates(path: Path | None = None) -> tuple[list[dict], list[str]]:
    path = path or CANDIDATES_CSV      # resolved at call time, not import time
    if path.exists():
        rows, fields = read_csv(path)
    else:
        rows, fields = [], list(BASE_COLS)
    for col in RESULT_COLS:
        if col not in fields:
            fields.append(col)
    for r in rows:
        for col in RESULT_COLS:
            if r.get(col) is None:
                r[col] = ""
    return rows, fields


def load_reviews_sidecar(path: Path | None = None) -> dict:
    path = path or CANDIDATE_REVIEWS_JSON
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(cands: list[dict], fields: list[str], sidecar: dict) -> None:
    write_csv(CANDIDATES_CSV, cands, fields)
    CANDIDATE_REVIEWS_JSON.write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")


def _key(row: dict) -> str:
    """Stable id for a candidate (manual rows may have no osm_id)."""
    return row.get("osm_id") or f"manual/{_squash(row.get('name', ''))}"


def add_candidate(cands: list[dict], name: str, area: str = "", store_type: str = "",
                  lat: str = "", lng: str = "") -> dict:
    """Append a hand-entered candidate (unverified until the next --verify)."""
    name = name.strip()
    if not name:
        raise ValueError("a store name is required")
    n = sum(1 for c in cands if str(c.get("osm_id", "")).startswith("manual/")) + 1
    row = {c: "" for c in BASE_COLS + RESULT_COLS}
    row.update({"osm_id": f"manual/{n}", "name": name, "locality_raw": area.strip(),
                "store_type": store_type or "retail_fashion", "lat": lat, "lng": lng})
    cands.append(row)
    return row


def unchecked(cands: list[dict]) -> list[dict]:
    """Rows still to verify — hand-added ones first, so a new store never
    waits behind the bulk backlog."""
    rows = [c for c in cands if not c.get("verified")]
    rows.sort(key=lambda c: not str(c.get("osm_id", "")).startswith("manual/"))
    return rows


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify(client, rows: list[dict], limit: int, on_progress=None,
           reviews: dict | None = None) -> Counter:
    """Check up to `limit` unchecked rows in place. Returns a status tally."""
    from .ml.google_places import PlacesBudgetExceeded, parse_reviews

    tally: Counter = Counter()
    reviews = reviews if reviews is not None else {}
    for row in rows:
        if sum(tally.values()) >= limit:
            break
        if row.get("verified"):
            continue
        query = " ".join(x for x in (row["name"], row.get("locality_raw"), "Bengaluru") if x)
        if _has_pin(row):
            lat, lng, radius = float(row["lat"]), float(row["lng"]), 500
        else:
            (lat, lng), radius = CITY_CENTER, CITY_RADIUS_M
        try:
            places = client.search_text(query, lat, lng, fields=SEARCH_FIELDS,
                                        radius_m=radius, page_size=5)
        except PlacesBudgetExceeded:
            break
        except Exception as e:
            # Quota used up for the day, key problem, network: leave this row
            # unchecked for the next run instead of failing the whole job.
            log.warning("Google check failed for %r (%s) — stopping verification for this run",
                        row["name"], e)
            break
        status, place, km, miss = pick_match(row, places)
        row["verified"] = status
        row["near_miss"] = miss
        row["checked_on"] = date.today().isoformat()
        if place:
            loc = place["location"]
            row.update({
                "place_id": place.get("id", ""),
                "google_name": (place.get("displayName") or {}).get("text", ""),
                "google_address": place.get("formattedAddress", ""),
                "google_lat": loc["latitude"], "google_lng": loc["longitude"],
                "google_rating": place.get("rating", ""),
                "google_review_count": place.get("userRatingCount", ""),
                "description": (place.get("editorialSummary") or {}).get("text", ""),
                "google_type": (place.get("primaryTypeDisplayName") or {}).get("text", ""),
                "google_phone": place.get("nationalPhoneNumber", ""),
                "match_km": "" if km is None else km,
            })
            if status == "verified":
                reviews[_key(row)] = [
                    {**r, "created_at": r["created_at"].isoformat() if r["created_at"] else ""}
                    for r in parse_reviews(place)]
        tally[status] += 1
        if on_progress:
            on_progress()
    return tally


# ---------------------------------------------------------------------------
# Promote
# ---------------------------------------------------------------------------

def _next_id(existing_ids: set[str]):
    n = max((int(m.group(1)) for i in existing_ids
             if (m := re.fullmatch(r"blr-(\d+)", i))), default=0)
    while True:
        n += 1
        yield f"blr-{n:04d}"


def promote(cands: list[dict], stores: list[dict], store_fields: list[str],
            reviews_sidecar: dict, review_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Turn verified, not-yet-promoted candidates into store rows (+ review rows).

    Mutates `cands` (sets promoted_id / marks duplicates), `stores` and
    `review_rows` in memory; the caller decides whether to write them.
    Returns (new_store_rows, new_review_rows).
    """
    for col in ("google_place_id", "description"):
        if col not in store_fields:
            store_fields.append(col)

    known_places = {s.get("google_place_id") for s in stores if s.get("google_place_id")}
    located = [(_squash(s["name"]), float(s["lat"]), float(s["lng"]))
               for s in stores if s.get("lat") and s.get("lng")]
    ids = _next_id({s["id"] for s in stores})
    rev_n = len(review_rows)
    new_stores, new_reviews = [], []

    for c in cands:
        if c.get("verified") != "verified" or c.get("promoted_id"):
            continue
        lat, lng = float(c["google_lat"]), float(c["google_lng"])
        name = c["google_name"] or c["name"]
        key = _squash(name)
        is_dup = c["place_id"] in known_places or any(
            haversine_km(lat, lng, la, lo) <= DUPLICATE_KM
            and min(len(key), len(k)) >= 4 and (key in k or k in key)
            for k, la, lo in located)
        if is_dup:
            c["verified"] = "duplicate"
            continue

        sid = next(ids)
        store = {f: "" for f in store_fields}
        store.update({
            "id": sid, "name": name,
            "locality_raw": c.get("locality_raw", ""), "city": "Bengaluru",
            "phone": c.get("google_phone") or c.get("phone", ""),
            "open_time": c.get("open_time", ""), "close_time": c.get("close_time", ""),
            "notes": "", "lat": lat, "lng": lng, "geocode_precision": "rooftop",
            "categories": str([c["google_type"]]) if c.get("google_type") else "[]",
            "verified_on": c.get("checked_on", ""),
            "store_type": c.get("store_type") or "retail_fashion",
            "rating": c.get("google_rating", ""),
            "review_count": c.get("google_review_count", ""),
            "address": c.get("google_address") or c.get("address", ""),
            "google_place_id": c["place_id"], "description": c.get("description", ""),
        })
        stores.append(store)
        new_stores.append(store)
        located.append((key, lat, lng))
        known_places.add(c["place_id"])
        c["promoted_id"] = sid

        for r in reviews_sidecar.get(_key(c), []):
            rev_n += 1
            row = {"review_id": f"rev-{rev_n:04d}", "store_id": sid, "store_name": name,
                   "author": r["author"], "rating": r["rating"], "review_text": r["text"],
                   "date": (r.get("created_at") or "")[:10], "source": "google_places_api"}
            review_rows.append(row)
            new_reviews.append(row)
    return new_stores, new_reviews


def promote_files(cands: list[dict], cand_fields: list[str], sidecar: dict,
                  write: bool) -> tuple[list[dict], list[dict]]:
    """promote() against the real CSV files; writes them only when `write`."""
    stores, store_fields = read_csv(STORES_CSV)
    review_rows, review_fields = read_csv(REVIEWS_CSV)
    new_stores, new_reviews = promote(cands, stores, store_fields, sidecar, review_rows)
    if write:
        if new_stores:
            write_csv(STORES_CSV, stores, store_fields)
            write_csv(REVIEWS_CSV, review_rows, review_fields)
        write_csv(CANDIDATES_CSV, cands, cand_fields)   # promoted ids / duplicate marks
    return new_stores, new_reviews


def status_line(cands: list[dict]) -> str:
    status = Counter(c.get("verified") or "unchecked" for c in cands)
    return (f"Candidates: {len(cands)} total | "
            + " | ".join(f"{k}: {v}" for k, v in sorted(status.items()))
            + f" | promoted: {sum(1 for c in cands if c.get('promoted_id'))}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Verify candidate stores with Google, then promote")
    ap.add_argument("--add", metavar="NAME", help="append a candidate store to be verified")
    ap.add_argument("--area", default="", help="with --add: neighbourhood, e.g. Indiranagar")
    ap.add_argument("--type", default="", dest="store_type",
                    choices=["", "thrift", "branded", "factory_outlet", "retail_fashion"],
                    help="with --add: kind of store")
    ap.add_argument("--lat", default="", help="with --add: latitude (optional)")
    ap.add_argument("--lng", default="", help="with --add: longitude (optional)")
    ap.add_argument("--verify", action="store_true", help="call Google for unchecked rows")
    ap.add_argument("--limit", type=int, default=50, help="max rows to verify this run")
    ap.add_argument("--only", choices=["branded", "factory_outlet", "retail_fashion", "thrift"],
                    help="verify only this kind of candidate")
    ap.add_argument("--promote", action="store_true", help="add verified rows to stores.csv")
    ap.add_argument("--write", action="store_true", help="with --promote: actually write the files")
    args = ap.parse_args()

    cands, cand_fields = load_candidates()
    sidecar = load_reviews_sidecar()

    if args.add:
        row = add_candidate(cands, args.add, args.area, args.store_type, args.lat, args.lng)
        write_csv(CANDIDATES_CSV, cands, cand_fields)
        print(f"Added candidate {row['osm_id']}: {row['name']} — it will be checked on the next --verify run.")

    if args.verify:
        from .config import GOOGLE_PLACES_API_KEY
        from .ml.google_places import PlacesClient
        if not GOOGLE_PLACES_API_KEY:
            raise SystemExit("GOOGLE_PLACES_API_KEY is not set. Add it to app/backend/.env "
                             "(a Google Cloud key with \"Places API (New)\" enabled).")
        client = PlacesClient(max_calls=args.limit)
        pool = [c for c in unchecked(cands) if not args.only or c.get("store_type") == args.only]
        try:
            tally = verify(client, pool, args.limit, reviews=sidecar,
                           on_progress=lambda: save_state(cands, cand_fields, sidecar))
        finally:
            save_state(cands, cand_fields, sidecar)
        print(f"Checked {sum(tally.values())} candidates with {client.calls} API calls: {dict(tally)}")

    if args.promote:
        new_stores, new_reviews = promote_files(cands, cand_fields, sidecar, args.write)
        verb = "Added" if args.write else "Would add"
        print(f"{verb} {len(new_stores)} stores and {len(new_reviews)} reviews:")
        for s in new_stores[:15]:
            print(f"    {s['id']}  {s['name']}  [{s['store_type']}]  {s['address'][:60]}")
        if len(new_stores) > 15:
            print(f"    ... and {len(new_stores) - 15} more")
        if args.write:
            print("WRITTEN. Run `python -m app.importer --write` to load them into the database.")
        else:
            print("DRY RUN — nothing written. Add --write to commit to the CSV files.")
            return      # the in-memory "promoted" marks were not saved; don't report them

    print(status_line(cands))


if __name__ == "__main__":
    main()

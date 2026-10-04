"""Seed the database from real data only.

  - Stores: data/stores.json  (real names, coords, timings, categories)

Everything seeded here comes from the source dataset — there is no synthetic
data. Fields the source doesn't provide are left blank:

  * reviews          → none; they accrue at runtime as users post them
  * experience_score → None until real reviews arrive
  * open/close time  → only where the source lists real hours, else blank
  * categories       → only the real labels the source provides, else blank
  * price            → not in the source, so left blank

Raw locality strings are canonicalised into clean area names, and stores
missing coordinates are backfilled from their area centroid so every store
still appears on the map and in a zone.

Run: python -m app.seed
"""
import json
import re

from .config import STORES_JSON
from .database import Base, SessionLocal, engine
from .ml import zones as zones_ml
from .models import Store, User, Zone

# System account used to attribute all externally-ingested reviews.
# auth_provider="system" distinguishes it from real users everywhere.
BOT_EMAIL = "reviews-bot@thriftfind.local"
BOT_NAME = "Reviews Bot"


# Canonical Bengaluru localities. Raw `locality_raw` values in the source
# data are messy ("J.P Nagar 5th Phase", "3rd Phase,JP Nagar", "Electronic
# City,Bengaluru", "Koramangala 8th Block"…), which fragmented the same
# neighbourhood into many "areas" and broke exact-match filtering. Any raw
# string containing one of these (ignoring case/punctuation/spacing) is
# collapsed to the canonical name.
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
    """Lowercase and drop everything but letters/digits, for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canonical_area(raw: str) -> str:
    """Map a raw locality string to a clean, canonical area name."""
    raw = (raw or "").strip()
    if not raw:
        return "Bengaluru"
    squashed = _squash(raw)
    for area in KNOWN_AREAS:
        if _squash(area) in squashed:
            return area
    # Fallback: strip a trailing ", Bengaluru", take the last comma segment
    # (usually the locality). If that segment is a bare generic suffix word
    # (e.g. "Bapuji,Nagar" -> "Nagar"), merge it with the preceding segment.
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


def _zone_rows(stores: list) -> list[dict]:
    """Shared builder for cluster_stores input — used by seed and pipeline so
    both call sites pass identical fields and can't drift from each other."""
    return [
        {
            "id": s.id,
            "lat": s.lat,
            "lng": s.lng,
            "area": s.area,
            "locality_raw": s.locality_raw,
            "price": (s.price_min + s.price_max) / 2 if s.price_min and s.price_max else None,
            "score": s.experience_score,
            "review_count": s.review_count,
        }
        for s in stores
    ]


def seed():
    """Seed the database inside a single transaction.

    Everything from table creation through the final commit either lands
    together or not at all — if this process is killed or raises partway
    through (crash, OOM, ctrl-C), the caller sees an empty/unchanged DB on
    the next startup instead of a half-seeded one.
    """
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        _seed_all(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _seed_all(db):
    # ---- 0. system bot user (for externally-ingested reviews) ----
    bot = User(email=BOT_EMAIL, name=BOT_NAME, auth_provider="system",
               password_hash=None)
    db.add(bot)
    db.flush()

    # ---- 1. stores (real data only) ----
    data = json.loads(STORES_JSON.read_text(encoding="utf-8"))
    stores = []
    for row in data["stores"]:
        closed_days = ""
        note = (row.get("notes") or "") + " " + (row.get("timing_note") or "")
        if "monday" in note.lower():
            closed_days = "Monday"
        # Sanitize implausible "00:00" opening times (midnight = bad/unknown
        # data, e.g. a 24h placeholder) so "open now" isn't falsely true.
        open_time = row.get("open_time")
        close_time = row.get("close_time")
        if open_time == "00:00":
            open_time = close_time = None
        raw_loc = row.get("locality_raw", "") or ""
        has_real_coords = row.get("lat") is not None and row.get("lng") is not None
        s = Store(
            id=row["id"], name=row["name"],
            area=canonical_area(raw_loc),
            city=row.get("city", "Bengaluru"),
            lat=row.get("lat"), lng=row.get("lng"),
            open_time=open_time, close_time=close_time,
            timing_note=row.get("timing_note"), notes=row.get("notes"),
            phone=row.get("phone"), instagram=row.get("instagram"),
            closed_days=closed_days,
            locality_raw=raw_loc or None,
            geocode_precision="locality" if has_real_coords else None,
            # Real categories only (comma-joined); blank when the source has none.
            categories=",".join(row.get("categories") or []),
            # No reviews / no price in the source — left blank. Real reviews and
            # the experience score they drive accrue at runtime via the API.
            experience_score=None,
            review_count=0,
        )
        stores.append(s)
        db.add(s)

    # Backfill missing coordinates from the centroid of same-area stores that
    # do have coordinates (locality-level precision, matching the dataset).
    # There is intentionally NO city-centre fallback: a store whose area has no
    # geocoded neighbour is left with NULL lat/lng. It stays in the DB but is
    # hidden from users and the map (see store visibility filter) until real
    # coordinates are pinned manually. Dumping such stores onto the city centre
    # put a false pin in the middle of Bengaluru, so that branch was removed.
    area_pts: dict[str, list] = {}
    for s in stores:
        if s.lat is not None and s.lng is not None:
            area_pts.setdefault(s.area, []).append((s.lat, s.lng))
    for s in stores:
        if s.lat is None or s.lng is None:
            pts = area_pts.get(s.area)
            if pts:
                s.lat = sum(p[0] for p in pts) / len(pts)
                s.lng = sum(p[1] for p in pts) / len(pts)
                s.geocode_precision = "centroid"
            # else: leave lat/lng NULL — no fallback pin.
    db.flush()

    # ---- 2. geospatial zones (clustered from real coordinates) ----
    zone_dicts = zones_ml.cluster_stores(_zone_rows(stores))
    for z in zone_dicts:
        zone = Zone(label=z["label"], center_lat=z["center_lat"],
                    center_lng=z["center_lng"], radius_km=z["radius_km"],
                    store_count=len(z["store_ids"]),
                    avg_score=z["avg_score"], avg_price=z["avg_price"],
                    description="")
        db.add(zone)
        db.flush()
        for sid in z["store_ids"]:
            db.get(Store, sid).zone_id = zone.id
    db.commit()

    n_cats = sum(1 for s in stores if s.categories)
    n_hours = sum(1 for s in stores if s.open_time)
    n_hidden = sum(1 for s in stores if s.lat is None or s.lng is None)
    print(
        f"Seeded: {len(stores)} stores ({len(stores) - n_hidden} visible, "
        f"{n_hidden} hidden — no coordinates, pending manual pin) | "
        f"{n_cats} with categories | {n_hours} with opening hours | 0 reviews | "
        f"{len(zone_dicts)} zones: {', '.join(z['label'] for z in zone_dicts)}"
    )


if __name__ == "__main__":
    # Explicit, destructive one-shot: drops and recreates every table, then
    # loads fresh data. Intentionally NOT run from app startup (see main.py).
    print("Seeding database (this DROPS and recreates all tables)...")
    seed()

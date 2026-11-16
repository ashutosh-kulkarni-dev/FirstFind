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

Run: python -m app.data.seed
"""
import json

from ..config import STORES_JSON
from ..database import Base, SessionLocal, engine
from ..ml import zones as zones_ml
from ..models import Store, User, Zone

from ..config import BOT_EMAIL, BOT_NAME
from ..common.areas import canonical_area
from ..ml.zones import zone_rows


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
    zone_dicts = zones_ml.cluster_stores(zone_rows(stores))
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

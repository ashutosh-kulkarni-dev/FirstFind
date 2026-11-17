"""Pillar 1 — Whole brain geo adapter.  Flag: CHAT_GEO

One public function:
    locate(db, entities) -> GeoResult

Resolves an area/locality name to a lat/lng, calls the existing find_cluster
engine, attaches the nearest metro station. This makes the chatbot use the
same geospatial engine as the map — chat and map can never disagree.

Imports: ml.clusters, routers.metro (load fn), contracts. Nothing from chat/.
"""
from __future__ import annotations

import json
import logging
import time
from functools import lru_cache
from typing import Optional

from sqlalchemy.orm import Session

from ..config import ASSETS_DIR
from ..ml.clusters import find_cluster
from ..models import Store
from ..common.serializers import STORE_HAS_COORDS
from ..common.geo import haversine_km
from .contracts import Entities, GeoResult

log = logging.getLogger(__name__)

_METRO_ASSET = ASSETS_DIR / "metro_stations_blr.json"

# Area centroid cache: canonical area name → (lat, lng) mean of its stores.
# Rebuilt hourly so stores the daily job adds, moves or hides are picked up
# without a restart (it used to be built once per process, forever).
_AREA_TTL_S = 3600
_area_coords: dict[str, tuple[float, float]] = {}
_area_coords_at = 0.0


def _ensure_area_coords(db: Session) -> dict[str, tuple[float, float]]:
    """The area→centroid map, built lazily from the DB and refreshed hourly."""
    global _area_coords, _area_coords_at
    if _area_coords and time.monotonic() - _area_coords_at < _AREA_TTL_S:
        return _area_coords
    _area_coords_at = time.monotonic()
    from collections import defaultdict
    buckets: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for s in db.query(Store).filter(*STORE_HAS_COORDS).all():
        if s.area:
            buckets[s.area].append((s.lat, s.lng))
    _area_coords = {
        area: (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        for area, pts in buckets.items()
    }
    return _area_coords


@lru_cache(maxsize=1)
def _load_metro() -> dict:
    if not _METRO_ASSET.exists():
        return {"lines": []}
    return json.loads(_METRO_ASSET.read_text(encoding="utf-8"))


def nearest_metro(lat: float, lng: float) -> Optional[dict]:
    data = _load_metro()
    best: Optional[dict] = None
    best_dist = float("inf")
    for line in data.get("lines", []):
        for st in line.get("stations", []):
            d = haversine_km(lat, lng, st["lat"], st["lng"])
            if d < best_dist:
                best_dist = d
                best = {
                    "name": st["name"],
                    "line_name": line["name"],
                    "line_color": line.get("color", "#888"),
                    "distance_m": round(d * 1000),
                    "lat": st["lat"],
                    "lng": st["lng"],
                }
    return best


def resolve_center(db: Session, entities: Entities,
                    origin: Optional[tuple[float, float]] = None) -> Optional[tuple[float, float]]:
    """Return (lat, lng) for the queried place, or None.

    Precedence:
      1. "near me" + browser origin supplied
      2. Store-area centroid (exact match)
      3. Gazetteer hit (B2)
      4. Locality fuzzy match fallback
    """
    # B3: "near me" with origin takes top priority
    if entities.near_me and origin is not None:
        return origin

    coords = _ensure_area_coords(db)
    if entities.area and entities.area in coords:
        return coords[entities.area]

    # B2: gazetteer hit
    if entities.place is not None:
        return (entities.place.lat, entities.place.lng)

    # Fallback: fuzzy match on locality_raw
    if entities.locality:
        loc_l = entities.locality.lower()
        for s in db.query(Store).filter(*STORE_HAS_COORDS).all():
            if s.locality_raw and loc_l in s.locality_raw.lower():
                return (s.lat, s.lng)
    return None


GEOGRAPHIC_INTENTS = {"find_by_area", "find_by_category", "find_by_price",
                      "open_now", "zone_exploration", "store_recommendation"}


def locate(db: Session, entities: Entities,
           radius_km: float = 2.0,
           origin: Optional[tuple[float, float]] = None) -> Optional[GeoResult]:
    """Main entry. Returns GeoResult or None if location can't be resolved.

    None means the engine falls back to the string-match retrieval path —
    exactly today's behaviour when CHAT_GEO is off.

    origin: (lat, lng) from browser geolocation, used only when near_me is True.
    """
    if entities.intent not in GEOGRAPHIC_INTENTS:
        return None
    # Accept if any location signal is present: area, locality, gazetteer hit, or near-me
    # ("near me" without an origin is no location: honest fallback, not a mis-bind.)
    has_location = (entities.area or entities.locality or entities.place is not None
                    or (entities.near_me and origin is not None))
    if not has_location:
        return None

    center = resolve_center(db, entities, origin=origin)
    if center is None:
        return None

    lat, lng = center
    try:
        cluster = find_cluster(db, lat, lng, radius_km)
    except Exception:
        # The assistant must still answer; the traceback is logged so a real
        # bug in clustering is visible instead of silently degrading replies.
        log.exception("geo.locate: find_cluster failed; falling back")
        return None

    store_ids = [s["id"] for s in cluster.get("stores", [])]
    nearest = nearest_metro(lat, lng)

    return GeoResult(
        center=(lat, lng),
        radius_km=cluster.get("radius_km", radius_km),
        store_ids=store_ids,
        nearest_metro=nearest,
    )

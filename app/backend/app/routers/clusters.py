"""Clusters router.

Phase 1 — GET  /api/clusters        : precomputed Zone rows (Mode A).
Phase 2 — GET  /api/clusters/find   : coordinate + radius live query (Mode B).
Phase 4 — GET  /api/clusters/split  : split an over-cap cluster into sub-zones.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import DEFAULT_MAX_SHOPS, DEFAULT_MIN_SHOPS, MAX_RADIUS_KM
from ..database import get_db
from ..ml.clusters import find_cluster, split_cluster
from ..models import Store, Zone
from ..utils import STORE_HAS_COORDS, haversine_km, zone_to_dict

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("")
def list_clusters(db: Session = Depends(get_db)):
    """Return all precomputed geographic zones (Mode A)."""
    return [zone_to_dict(z) for z in db.query(Zone).all()]


@router.get("/find")
def find(
    lat: float,
    lng: float,
    radius_km: float = 2.0,
    min_shops: int = DEFAULT_MIN_SHOPS,
    max_shops: int = DEFAULT_MAX_SHOPS,
    db: Session = Depends(get_db),
):
    """Mode B: find stores within radius of a coordinate."""
    if radius_km <= 0 or radius_km > MAX_RADIUS_KM:
        raise HTTPException(400, f"radius_km must be between 0 and {MAX_RADIUS_KM}")
    if min_shops < 1:
        raise HTTPException(400, "min_shops must be >= 1")
    if max_shops < min_shops:
        raise HTTPException(400, "max_shops must be >= min_shops")
    return find_cluster(db, lat, lng, radius_km, min_shops, max_shops)


@router.get("/split")
def split(
    lat: float,
    lng: float,
    radius_km: float,
    max_shops: int = DEFAULT_MAX_SHOPS,
    db: Session = Depends(get_db),
):
    """Split an over-cap cluster into sub-zones.

    Takes the same center + radius as /find, re-fetches the stores inside,
    and returns a list of sub-zone dicts (same shape as find_cluster output).

    Invariant: union of all sub-zone store_ids == stores within radius (no drop).
    """
    if radius_km <= 0 or radius_km > MAX_RADIUS_KM:
        raise HTTPException(400, f"radius_km must be between 0 and {MAX_RADIUS_KM}")
    if max_shops < 2:
        raise HTTPException(400, "max_shops must be >= 2")

    stores_in = [
        s for s in db.query(Store).filter(*STORE_HAS_COORDS).all()
        if haversine_km(lat, lng, s.lat, s.lng) <= radius_km
    ]

    if len(stores_in) < 2:
        raise HTTPException(400, "Need at least 2 stores to split")

    sub_zones = split_cluster(stores_in, lat, lng, max_shops)
    return {"sub_zones": sub_zones, "count": len(sub_zones)}

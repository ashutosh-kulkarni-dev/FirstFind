"""Metro overlay router — Phase 5.

Serves the static Purple + Green line station data from data/metro_stations_blr.json.
No DB reads — the asset is loaded once at import time and kept in memory.

GET /api/metro/stations          — full line + station list for map overlay.
GET /api/metro/nearest?lat&lng   — nearest station + haversine distance for a coordinate.
"""
import json
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, HTTPException

from ..config import REPO_ROOT
from ..utils import haversine_km

router = APIRouter(prefix="/api/metro", tags=["metro"])

_ASSET = REPO_ROOT / "data" / "metro_stations_blr.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not _ASSET.exists():
        raise FileNotFoundError(f"Metro asset missing: {_ASSET}")
    return json.loads(_ASSET.read_text(encoding="utf-8"))


@router.get("/stations")
def stations():
    """Return all metro lines with ordered station lists and line colour."""
    return _load()


@router.get("/nearest")
def nearest(lat: float, lng: float):
    """Return the nearest metro station to (lat, lng) with haversine distance."""
    data = _load()
    best = None
    best_dist = float("inf")
    for line in data["lines"]:
        for st in line["stations"]:
            d = haversine_km(lat, lng, st["lat"], st["lng"])
            if d < best_dist:
                best_dist = d
                best = {
                    "name": st["name"],
                    "lat": st["lat"],
                    "lng": st["lng"],
                    "line_id": line["id"],
                    "line_name": line["name"],
                    "line_color": line["color"],
                    "distance_km": round(d, 3),
                    "distance_m": round(d * 1000),
                }
    if best is None:
        raise HTTPException(500, "Metro asset is empty")
    return best

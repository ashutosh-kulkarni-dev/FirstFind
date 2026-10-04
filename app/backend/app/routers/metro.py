"""Metro overlay router — Phase 5.

Serves the static Purple + Green line station data from data/metro_stations_blr.json.
No DB reads — the asset is loaded once at import time and kept in memory.

GET /api/metro/stations          — full line + station list for map overlay.
GET /api/metro/nearest?lat&lng   — nearest station + haversine distance for a coordinate.
"""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import REPO_ROOT
from ..utils import haversine_km

router = APIRouter(prefix="/api/metro", tags=["metro"])

# Prefer the package-local copy (always shipped by the Docker image via
# `COPY app ./app`); fall back to the repo-root data dir for local dev checkouts
# that still edit the authoritative file there. Keep both in sync — the refresh
# script writes to data/ and the vendoring step mirrors it into the package.
_PACKAGE_ASSET = Path(__file__).resolve().parent.parent / "metro_stations_blr.json"
_REPO_ASSET = REPO_ROOT / "data" / "metro_stations_blr.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    for candidate in (_PACKAGE_ASSET, _REPO_ASSET):
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"Metro asset missing in both {_PACKAGE_ASSET} and {_REPO_ASSET}")


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

"""Pillar 4 — Map render spec builder.  Flag: CHAT_MAP

Pure function — no DB, no state, no I/O.

    build(geo, trip, stores) -> (map_spec | None, action | None)

map_spec: passed to the frontend ChatCore, which renders a read-only MiniMap.
action:   a deep-link directive — frontend shows "View on full map →" button
          that opens /zones with the cluster pre-configured.

Imports: contracts only.
"""
from __future__ import annotations

from typing import Optional

from .contracts import GeoResult, Trip

GEOGRAPHIC_INTENTS = {"find_by_area", "find_by_category", "find_by_price",
                      "open_now", "zone_exploration", "store_recommendation",
                      "review_insight"}


def build(
    geo: Optional[GeoResult],
    trip: Optional[Trip],
    stores: list[dict],
    intent: str,
) -> tuple[Optional[dict], Optional[dict]]:
    """Return (map_spec, action) or (None, None) if not applicable.

    map_spec shape (consumed by <MiniMap> in ChatCore.jsx):
    {
        center: [lat, lng],
        radius_km: float,
        stores: [{id, name, lat, lng, is_open_now}],
        metro: {name, line_name, line_color, distance_m} | null,
    }

    action shape (consumed by ChatCore.jsx to render the deep-link button):
    {
        type: "open_zones",
        label: "View on full map →",
        params: {lat, lng, radius_km},
    }
    """
    if intent not in GEOGRAPHIC_INTENTS:
        return None, None

    # We need a center to render a map
    center = None
    radius_km = None
    metro = None

    if geo and geo.center:
        center = list(geo.center)
        radius_km = geo.radius_km or 2.0
        metro = geo.nearest_metro
    elif trip and trip.center:
        center = list(trip.center)
        radius_km = trip.radius_km or 2.0

    if center is None and stores:
        # Fall back to centroid of returned stores
        lats = [s["lat"] for s in stores if s.get("lat")]
        lngs = [s["lng"] for s in stores if s.get("lng")]
        if lats:
            center = [sum(lats) / len(lats), sum(lngs) / len(lngs)]
            radius_km = 2.0

    if center is None:
        return None, None

    map_stores = [
        {
            "id": s.get("id"),
            "name": s.get("name"),
            "lat": s.get("lat"),
            "lng": s.get("lng"),
            "is_open_now": s.get("is_open_now"),
        }
        for s in stores
        if s.get("lat") and s.get("lng")
    ]

    map_spec = {
        "center": center,
        "radius_km": radius_km,
        "stores": map_stores,
        "metro": metro,
    }

    action = {
        "type": "open_zones",
        "label": "View on full map →",
        "params": {"lat": center[0], "lng": center[1], "radius_km": radius_km},
    }

    return map_spec, action

"""Pillar 3 — Trip builder and refiner.  Flag: CHAT_TRIPS

Pure functions — no DB, no state, no I/O. Given stores + optional geo context,
returns a coherent shopping Trip. Refinement returns a *new* Trip (immutable-style).

Imports: contracts only.
"""
from __future__ import annotations

import re
from typing import Optional

from .contracts import Entities, GeoResult, Prefs, Trip

MAX_TRIP_SIZE = 5
MIN_TRIP_SIZE = 2


def build(stores: list[dict], geo: Optional[GeoResult],
          prefs: Optional[Prefs] = None) -> Trip:
    """Shape a candidate shopping trip from a ranked store list.

    When geo is present (Pillar 1), stores inside the cluster are preferred
    and the trip is geographically coherent (walkable set). Without geo,
    just take the top MAX_TRIP_SIZE stores from the ranked list.
    """
    if not stores:
        return Trip()

    if geo and geo.store_ids:
        geo_ids = set(geo.store_ids)
        # Split into in-cluster and out-of-cluster, preserve ranking order
        in_cluster = [s for s in stores if s.get("id") in geo_ids]
        out_cluster = [s for s in stores if s.get("id") not in geo_ids]
        # Fill up to MAX_TRIP_SIZE: prefer in-cluster, pad with out if needed
        selected = (in_cluster + out_cluster)[:MAX_TRIP_SIZE]
        center = geo.center
        radius_km = geo.radius_km
    else:
        selected = stores[:MAX_TRIP_SIZE]
        center = None
        radius_km = None

    store_ids = [s["id"] for s in selected if s.get("id")]

    # Build an origin label from the first store's area or the geo cluster label
    origin_label = None
    if selected:
        area = selected[0].get("area")
        if area:
            origin_label = f"{area} thrift run"

    return Trip(
        store_ids=store_ids,
        center=center,
        radius_km=radius_km,
        origin_label=origin_label,
    )


def refine(trip: Trip, op: str, all_stores: list[dict],
           entities: Optional[Entities] = None) -> Trip:
    """Apply a refinement operation to the current trip. Returns a new Trip.

    ops: "cheaper", "open_only", "drop", "add_area", "reorder"
    all_stores: the full ranked candidate pool (same as retrieval returned).
    """
    if not trip.store_ids:
        return trip

    store_index = {s["id"]: s for s in all_stores if s.get("id")}
    current = [store_index[sid] for sid in trip.store_ids if sid in store_index]

    if op == "cheaper":
        # Drop the most expensive store from the trip
        def price_key(s: dict) -> float:
            return float(s.get("price_min") or 9999)
        expensive = max(current, key=price_key, default=None)
        new_ids = [sid for sid in trip.store_ids
                   if not expensive or sid != expensive.get("id")]
        # Optionally pad from the pool
        pool_ids = {s["id"] for s in all_stores}
        trip_set = set(new_ids)
        for s in all_stores:
            if len(new_ids) >= MAX_TRIP_SIZE:
                break
            if s["id"] not in trip_set and s["id"] in pool_ids:
                p = s.get("price_min")
                if p is not None:
                    threshold = price_key(expensive) if expensive else 9999
                    if p < threshold:
                        new_ids.append(s["id"])
                        trip_set.add(s["id"])
        return Trip(store_ids=new_ids, center=trip.center,
                    radius_km=trip.radius_km, origin_label=trip.origin_label)

    elif op == "open_only":
        new_ids = [s["id"] for s in current if s.get("is_open_now") is True]
        if not new_ids:
            new_ids = trip.store_ids  # don't empty the trip if nothing confirmed open
        return Trip(store_ids=new_ids, center=trip.center,
                    radius_km=trip.radius_km, origin_label=trip.origin_label)

    elif op == "drop":
        # Drop the last store (or could parse a name — simple heuristic for now)
        new_ids = trip.store_ids[:-1] if len(trip.store_ids) > MIN_TRIP_SIZE else trip.store_ids
        return Trip(store_ids=new_ids, center=trip.center,
                    radius_km=trip.radius_km, origin_label=trip.origin_label)

    elif op == "reorder":
        # Nearest-neighbour ordering from the trip center or first store
        return _nearest_neighbour_order(trip, current)

    # Default: return unchanged
    return trip


def _nearest_neighbour_order(trip: Trip, stores: list[dict]) -> Trip:
    """Greedy nearest-neighbour ordering — pure haversine, no external routing."""
    if len(stores) <= 1:
        return trip

    def hav(a: dict, b: dict) -> float:
        import math
        lat1, lng1 = a.get("lat", 0), a.get("lng", 0)
        lat2, lng2 = b.get("lat", 0), b.get("lng", 0)
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lng2 - lng1)
        aa = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(aa))

    # Start from the store closest to the trip center, or the first store
    remaining = list(stores)
    if trip.center:
        anchor = {"lat": trip.center[0], "lng": trip.center[1], "id": "__center__"}
        remaining.sort(key=lambda s: hav(anchor, s))
    ordered = [remaining.pop(0)]
    while remaining:
        last = ordered[-1]
        nearest = min(remaining, key=lambda s: hav(last, s))
        ordered.append(nearest)
        remaining.remove(nearest)

    return Trip(
        store_ids=[s["id"] for s in ordered],
        center=trip.center,
        radius_km=trip.radius_km,
        origin_label=trip.origin_label,
    )


def itinerary_text(trip: Trip, stores: list[dict]) -> str:
    """Format the ordered trip as a numbered text itinerary."""
    store_index = {s["id"]: s for s in stores if s.get("id")}
    lines = []
    for i, sid in enumerate(trip.store_ids, 1):
        s = store_index.get(sid)
        if not s:
            continue
        name = s.get("name", sid)
        area = s.get("area", "")
        price = ""
        if s.get("price_min") is not None:
            price = f" · ₹{s['price_min']}–{s.get('price_max', '?')}"
        open_str = " · open now" if s.get("is_open_now") is True else ""
        lines.append(f"{i}. **{name}** ({area}){price}{open_str}")
    return "\n".join(lines) if lines else ""

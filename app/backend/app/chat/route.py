"""Walkable shopping routes.

    plan(start, stores) -> Route

Orders the stores into a short walking route from a starting point:
nearest-neighbour first, then 2-opt swaps until no swap shortens it. Walking
distance is straight-line distance times a street-detour factor; there is no
routing service behind this, so legs are labelled as approximate ("~").

Pure functions — no DB, no state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..common.geo import haversine_km

DETOUR = 1.3              # streets are longer than a straight line
WALK_M_PER_MIN = 78       # ~4.7 km/h, an unhurried shopping pace
MAX_STOPS = 5


@dataclass
class Stop:
    id: str
    name: str
    area: str
    lat: float
    lng: float
    walk_m: int           # from the previous stop (or the start)
    walk_min: int


@dataclass
class Route:
    start: tuple[float, float]
    start_label: str
    stops: list[Stop] = field(default_factory=list)
    start_metro: Optional[dict] = None    # nearest station to the start
    end_metro: Optional[dict] = None      # nearest station to the last stop

    @property
    def total_m(self) -> int:
        return sum(s.walk_m for s in self.stops)

    @property
    def total_min(self) -> int:
        return sum(s.walk_min for s in self.stops)

    def to_dict(self) -> dict:
        return {
            "start": list(self.start), "start_label": self.start_label,
            "total_m": self.total_m, "total_min": self.total_min,
            "stops": [s.__dict__ for s in self.stops],
            "start_metro": self.start_metro, "end_metro": self.end_metro,
        }


def walk_m(a: tuple[float, float], b: tuple[float, float]) -> int:
    return int(round(haversine_km(a[0], a[1], b[0], b[1]) * 1000 * DETOUR))


def _length(start, pts) -> float:
    total, prev = 0.0, start
    for p in pts:
        total += haversine_km(prev[0], prev[1], p[0], p[1])
        prev = p
    return total


def order(start: tuple[float, float], points: list[tuple[float, float]]) -> list[int]:
    """Indices of `points` in visiting order: an open path from `start`."""
    remaining = list(range(len(points)))
    path: list[int] = []
    here = start
    while remaining:
        nxt = min(remaining, key=lambda i: haversine_km(here[0], here[1], *points[i]))
        path.append(nxt)
        remaining.remove(nxt)
        here = points[nxt]
    # 2-opt: reverse any stretch of the path that makes the walk shorter.
    improved = True
    while improved:
        improved = False
        for i in range(len(path) - 1):
            for j in range(i + 1, len(path)):
                candidate = path[:i] + path[i:j + 1][::-1] + path[j + 1:]
                if _length(start, [points[k] for k in candidate]) + 1e-9 < \
                        _length(start, [points[k] for k in path]):
                    path, improved = candidate, True
    return path


def plan(start: tuple[float, float], start_label: str, stores: list,
         nearest_metro=None, within_km: float = 1.2) -> Route:
    """stores: candidate Store rows, best first. The best MAX_STOPS within
    `within_km` of the start are used, then put in walking order.
    nearest_metro: fn(lat, lng) -> station dict, for the start and end."""
    chosen = [s for s in stores if s.lat is not None and s.lng is not None
              and haversine_km(start[0], start[1], s.lat, s.lng) <= within_km][:MAX_STOPS]
    pts = [(s.lat, s.lng) for s in chosen]
    route = Route(start=start, start_label=start_label)
    prev = start
    for i in order(start, pts):
        s = chosen[i]
        m = walk_m(prev, pts[i])
        route.stops.append(Stop(id=s.id, name=s.name, area=s.area or "", lat=s.lat, lng=s.lng,
                                walk_m=m, walk_min=max(1, round(m / WALK_M_PER_MIN))))
        prev = pts[i]
    if nearest_metro:
        route.start_metro = nearest_metro(*start)
        if route.stops:
            last = route.stops[-1]
            route.end_metro = nearest_metro(last.lat, last.lng)
    return route


def distance_text(m: int) -> str:
    return f"{m} m" if m < 1000 else f"{m / 1000:.1f} km"


def route_text(route: Route) -> str:
    """The reply for a planned route: a warm line, the numbered stops, metro."""
    if not route.stops:
        return ""
    if len(route.stops) == 1:
        s = route.stops[0]
        lines = [f"Only one store is an easy walk from {route.start_label}: {s.name}, "
                 f"~{distance_text(s.walk_m)} ({s.walk_min} min) away."]
    else:
        lines = [f"Here's a walkable route from {route.start_label} — about "
                 f"{distance_text(route.total_m)}, ~{route.total_min} min on foot:"]
    for n, s in enumerate(route.stops if len(route.stops) > 1 else [], 1):
        leg = ("right next door" if s.walk_m < 40 and n > 1
               else f"~{distance_text(s.walk_m)}, {s.walk_min} min")
        lines.append(f"{n}. {s.name} — {leg}")
    sm, em = route.start_metro, route.end_metro
    if sm and sm.get("distance_m", 99999) <= 2000:
        lines.append(f"🚇 Nearest metro: {sm['name']} ({sm['line_name']}), "
                     f"{distance_text(sm['distance_m'])} from the start.")
    if em and sm and em.get("name") != sm.get("name") and em.get("distance_m", 99999) <= 2000:
        lines.append(f"Heading home? {em['name']} is {distance_text(em['distance_m'])} from the last stop.")
    return "\n".join(lines)

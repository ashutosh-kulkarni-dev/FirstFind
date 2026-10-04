"""Shared typed contracts for the chat package.

Leaf module — imports nothing from chat/. All other chat modules exchange
these dataclasses rather than importing each other's internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .places import PlaceHit


@dataclass(frozen=True)
class Entities:
    """Output of Stage-1 understand. Everything the retriever needs."""
    intent: str
    area: str | None = None
    locality: str | None = None
    category: str | None = None
    price_max: int | None = None
    store_names: list[str] = field(default_factory=list)
    open_now: bool = False
    # B2: gazetteer hit — (canonical, lat, lng) or None
    place: Optional[object] = None   # PlaceHit namedtuple; typed as object to stay a leaf
    # B3: user said "near me" (browser geolocation will supply origin)
    near_me: bool = False


@dataclass(frozen=True)
class GeoResult:
    """Output of geo.py — geospatially-coherent store set + metro context."""
    center: tuple[float, float] | None        # (lat, lng)
    radius_km: float | None
    store_ids: list[str]
    nearest_metro: dict | None                # {name, line_name, line_color, distance_m} | None


@dataclass
class Trip:
    """The mutable shopping plan. Only thing persisted in session state."""
    store_ids: list[str] = field(default_factory=list)
    center: tuple[float, float] | None = None
    radius_km: float | None = None
    origin_label: str | None = None           # e.g. "Koramangala thrift run"

    def to_dict(self) -> dict:
        return {
            "store_ids": self.store_ids,
            "center": list(self.center) if self.center else None,
            "radius_km": self.radius_km,
            "origin_label": self.origin_label,
        }


@dataclass
class Prefs:
    """Explicitly stated user preferences — applied as soft ranking boosts only."""
    liked_categories: list[str] = field(default_factory=list)
    disliked_categories: list[str] = field(default_factory=list)
    budget_ceiling: int | None = None
    home_area: str | None = None


@dataclass
class ChatSession:
    """Everything remembered across turns for one session."""
    last_entities: Entities | None = None
    current_trip: Trip | None = None
    prefs: Prefs = field(default_factory=Prefs)


@dataclass
class Draft:
    """What a handler produces before LLM phrasing."""
    reply: str
    stores: list        # list[Store ORM objects]
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ChatResult:
    """What engine.respond() returns — superset of today's API shape.

    map and action are optional new fields; old clients ignore them.
    trip is the serialized Trip for frontend state sync.
    """
    reply: str
    intent: str
    stores: list[dict]
    suggestions: list[str]
    map: dict | None = None       # Pillar 4 — mini-map render spec
    action: dict | None = None    # Pillar 4 — deep-link directive
    trip: dict | None = None      # Pillar 3 — serialized Trip

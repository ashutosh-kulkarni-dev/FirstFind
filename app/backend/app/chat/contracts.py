"""Shared typed contracts for the chat package.

Leaf module — imports nothing from chat/. All other chat modules exchange
these dataclasses rather than importing each other's internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


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
    # Shopping slots (slots.py): store kind, who it's for, style tag, price tier
    store_kind: str | None = None
    audience: str | None = None
    style: str | None = None
    price_tier: str | None = None


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
    # Answers to the assistant's questions — remembered for the conversation
    # and, for a logged-in user, across visits (User.chat_prefs).
    price_tier: str | None = None
    audience: str | None = None
    store_kind: str | None = None

    def remembered(self) -> dict:
        return {k: v for k, v in (("price_tier", self.price_tier), ("audience", self.audience),
                                  ("store_kind", self.store_kind)) if v}


@dataclass
class ChatSession:
    """Everything remembered across turns for one session."""
    last_entities: Entities | None = None
    current_trip: Trip | None = None
    prefs: Prefs = field(default_factory=Prefs)
    pending: Optional[object] = None      # slots.Pending while waiting on an answer
    prefs_loaded: bool = False            # a logged-in user's saved answers applied


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
    # A clarifying question: {slot, question, options: [{label, value}], skip}
    clarify: dict | None = None
    route: list | None = None     # ordered trip stops with walking legs

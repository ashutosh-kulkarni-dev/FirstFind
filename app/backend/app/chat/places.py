"""Pillar B2 — Bengaluru place gazetteer.

Leaf module: imports nothing from chat/. Resolves a normalized query string
to a known Bengaluru locality/road using longest-alias-first substring match.
Data is loaded once from data/bengaluru_places.json via lru_cache.

Public API:
    resolve_place(norm: str) -> Optional[PlaceHit]
    PlaceHit = namedtuple("PlaceHit", ["canonical", "lat", "lng"])
"""
from __future__ import annotations

import json
import logging
from collections import namedtuple
from functools import lru_cache
from typing import Optional

from ..config import REPO_ROOT

log = logging.getLogger(__name__)

PlaceHit = namedtuple("PlaceHit", ["canonical", "lat", "lng"])

_PLACES_ASSET = REPO_ROOT / "data" / "bengaluru_places.json"


@lru_cache(maxsize=1)
def _load_places() -> list[tuple[str, str, float, float]]:
    """Return list of (alias, canonical, lat, lng) sorted longest-alias first."""
    if not _PLACES_ASSET.exists():
        log.warning("places: %s not found — gazetteer disabled", _PLACES_ASSET)
        return []
    raw = json.loads(_PLACES_ASSET.read_text(encoding="utf-8"))
    entries = []
    for rec in raw:
        for alias in rec.get("aliases", []):
            entries.append((alias.lower(), rec["canonical"], rec["lat"], rec["lng"]))
    # longest alias first so "mahatma gandhi road" matches before "road"
    entries.sort(key=lambda e: len(e[0]), reverse=True)
    return entries


def resolve_place(norm: str) -> Optional[PlaceHit]:
    """Return PlaceHit if norm contains a known Bengaluru place alias, else None."""
    for alias, canonical, lat, lng in _load_places():
        if alias in norm:
            return PlaceHit(canonical=canonical, lat=lat, lng=lng)
    return None

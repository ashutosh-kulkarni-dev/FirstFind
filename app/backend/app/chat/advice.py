"""Standalone SHOP advice module.  Flag: CHAT_ADVICE

Pure lookup over data/thrift_advice.json — no DB, no state, no I/O at call time
(file loaded once at import). A new `shopping_advice` intent handler calls this;
the engine also garnishes category discovery results with a short tip.

Imports: nothing from chat/ (truly independent).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "thrift_advice.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("advice: failed to load thrift_advice.json (%s)", e)
        return {"topics": [], "category_tips": {}, "general_tip": ""}


def lookup(query: str) -> str:
    """Return the most relevant thrift advice tip for the query text.

    Scores each topic by keyword overlap with the lowercased query.
    Falls back to the general tip if nothing matches.
    """
    data = _load()
    q = query.lower()
    best_tip = data.get("general_tip", "")
    best_score = 0

    for topic in data.get("topics", []):
        score = sum(1 for kw in topic.get("keywords", []) if kw in q)
        if score > best_score:
            best_score = score
            best_tip = topic.get("tip", best_tip)

    return best_tip


def category_tip(category: Optional[str]) -> Optional[str]:
    """Return a short contextual tip for a category discovery result, or None."""
    if not category:
        return None
    data = _load()
    return data.get("category_tips", {}).get(category)

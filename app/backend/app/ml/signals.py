"""Record what a user did with a store, for the recommender.

view  — opened the store page (deduplicated per day by the store route)
save  — saved it, or put it in one of their lists
like  — gave it a 4 or 5 star review
"""
from __future__ import annotations

from ..models import Interaction

LIKE_FROM_RATING = 4


def record(db, user_id: int, store_id: str, kind: str) -> bool:
    """Add a save / like once per user and store. Returns True if it was new.
    Does not commit."""
    exists = (db.query(Interaction.id)
              .filter(Interaction.user_id == user_id, Interaction.store_id == store_id,
                      Interaction.kind == kind)
              .first())
    if exists:
        return False
    db.add(Interaction(user_id=user_id, store_id=store_id, kind=kind))
    return True

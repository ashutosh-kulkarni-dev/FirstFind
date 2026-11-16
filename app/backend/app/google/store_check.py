"""Daily store verification: check the stores we already list against Google.

For each store (the ones checked longest ago first) one Google Places call
answers three questions:

  * is it still on Google under (roughly) this name, at this spot?
  * is it permanently closed?  -> the store is switched off (hidden)
  * what is its Google rating / number of ratings now?  -> refreshed

It never adds a store and never deletes one. A store Google cannot find is
only reported, not hidden — a missing listing is not proof the shop is gone.

One call per store, so a key limited to 100 calls/day covers 90 stores a day
and the whole list roughly once a week.
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..models import Store
from .candidates import name_similarity

log = logging.getLogger(__name__)

NAME_MATCH = 0.75           # same threshold as candidate verification
SEARCH_RADIUS_M = 300
_FIELDS = "displayName,rating,userRatingCount,businessStatus"
_SEARCH_FIELDS = "places.id," + ",".join("places." + f for f in _FIELDS.split(","))


def _place_name(place: dict) -> str:
    return (place.get("displayName") or {}).get("text") or ""


def _find(client, store: Store) -> dict | None:
    """The store's Google listing, or None. Uses the saved place id when there
    is one; otherwise a text search near the pin, accepted only on a name match."""
    if store.google_place_id:
        return client.details(store.google_place_id, _FIELDS)
    places = client.search_text(
        f"{store.name} {store.locality_raw or store.area} {store.city or 'Bengaluru'}",
        store.lat, store.lng, fields=_SEARCH_FIELDS, radius_m=SEARCH_RADIUS_M, page_size=3)
    for place in places or []:
        if name_similarity(store.name, _place_name(place)) >= NAME_MATCH:
            store.google_place_id = place.get("id")
            return place
    return None


def verify_stores(db, client, limit: int | None = None) -> dict:
    """Check as many stores as the client's call budget allows. Commits as it goes."""
    from .places import PlacesBudgetExceeded

    stores = [s for s in db.query(Store).all()
              if s.lat is not None and s.lng is not None and s.is_active is not False]
    stores.sort(key=lambda s: (s.reviews_fetched_at is not None,
                               s.reviews_fetched_at or datetime.min, s.id))
    if limit:
        stores = stores[:limit]

    confirmed = errors = 0
    closed: list[str] = []
    not_found: list[str] = []
    for n, store in enumerate(stores, 1):
        try:
            place = _find(client, store)
        except PlacesBudgetExceeded:
            log.info("Google call budget used up — the rest wait for the next run")
            break
        except Exception as e:                      # quota / network: try again tomorrow
            errors += 1
            log.warning("Google error on %s: %s", store.id, str(e)[:160])
            if errors >= 3:
                log.error("Google is failing repeatedly — stopping verification for this run")
                break
            continue

        store.reviews_fetched_at = datetime.utcnow()
        if place is None:
            not_found.append(f"{store.id} {store.name}")
        else:
            confirmed += 1
            if place.get("rating") is not None:
                store.google_rating = float(place["rating"])
            if place.get("userRatingCount") is not None:
                store.google_review_count = int(place["userRatingCount"])
            if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                store.is_active = False
                closed.append(f"{store.id} {store.name}")
        if n % 10 == 0:
            db.commit()
    db.commit()

    result = {"checked": confirmed + len(not_found), "confirmed": confirmed,
              "closed_and_hidden": closed, "not_found_on_google": not_found,
              "errors": errors, "api_calls": client.calls,
              "still_to_check": sum(1 for s in stores if s.reviews_fetched_at is None)}
    log.info("Store verification: %s", result)
    return result

"""What the API sends for a store, a zone and a review summary — and which
stores are visible at all."""
from typing import Optional

from ..models import Store, Zone
from .geo import haversine_km
from .hours import is_open_now

# Store visibility policy: a store is shown to users (and placed on the map)
# only once it has real coordinates. Stores whose location couldn't be geocoded
# are kept in the DB — for manual pinning — but hidden from every user-facing
# store listing until lat/lng are filled in. Spread these expressions into a
# query with `query.filter(*STORE_HAS_COORDS)`; adding coords un-hides a store
# automatically (no flag to flip).
# `is_active IS NOT FALSE` (rather than `IS TRUE`) so rows that predate the
# column — where it may be NULL — stay visible.
STORE_HAS_COORDS = (Store.lat.isnot(None), Store.lng.isnot(None),
                    Store.is_active.isnot(False))


def has_coords(store: Store) -> bool:
    """In-Python equivalent of STORE_HAS_COORDS for already-loaded objects."""
    return (store is not None and store.lat is not None
            and store.lng is not None and store.is_active is not False)


def sentiment_summary(reviews: list) -> dict:
    """Count reviews by sentiment label. `reviews`: any objects with `.sentiment`.

    Shared by the store detail endpoint and the chatbot so the summary shape
    ({positive, neutral, negative, total}) is defined in exactly one place.
    """
    pos = sum(1 for r in reviews if r.sentiment == "positive")
    neg = sum(1 for r in reviews if r.sentiment == "negative")
    neu = sum(1 for r in reviews if r.sentiment == "neutral")
    # Counts, not percentages. `unscored` = sentiment not computed yet; it used
    # to be folded into `neutral`, which made a store look 100% neutral.
    return {"positive": pos, "neutral": neu, "negative": neg,
            "unscored": len(reviews) - pos - neg - neu, "total": len(reviews)}


def store_to_dict(store: Store, user_lat=None, user_lng=None) -> dict:
    from ..ml.descriptions import describe   # local: avoids an import cycle
    description, description_source = describe(store)
    d = {
        "id": store.id,
        "name": store.name,
        "area": store.area,
        "lat": store.lat,
        "lng": store.lng,
        "open_time": store.open_time,
        "close_time": store.close_time,
        "timing_note": store.timing_note,
        "notes": store.notes,
        "phone": store.phone,
        "instagram": store.instagram,
        "categories": [c for c in (store.categories or "").split(",") if c],
        "closed_days": [c for c in (store.closed_days or "").split(",") if c],
        "price_min": store.price_min,
        "price_max": store.price_max,
        "experience_score": round(store.experience_score, 2) if store.experience_score else None,
        "review_count": store.review_count or 0,
        "zone_id": store.zone_id,
        "is_open_now": is_open_now(store),
        "store_type": store.store_type or "thrift",
        "tags": [t for t in (store.tags or "").split(",") if t],
        "address": store.address,
        "description": description,
        # "google" | "ai" | "admin" | "auto" (plain line built from category + area)
        "description_source": description_source,
        "google_rating": store.google_rating,
        "google_review_count": store.google_review_count,
        "price_estimated": bool(store.price_estimated),
    }
    if user_lat is not None and user_lng is not None and store.lat and store.lng:
        d["distance_km"] = round(haversine_km(user_lat, user_lng, store.lat, store.lng), 2)
    return d


def zone_to_dict(zone: Zone, stores: Optional[list] = None) -> dict:
    """Canonical Zone serializer — single source of truth for /api/zones,
    /api/clusters, and the chatbot. Pass `stores` to include top_stores."""
    d = {
        "id": zone.id,
        "label": zone.label,
        "center_lat": zone.center_lat,
        "center_lng": zone.center_lng,
        "radius_km": zone.radius_km,
        "store_count": zone.store_count,
        "avg_score": zone.avg_score,
        "avg_price": zone.avg_price,
        "description": zone.description,
    }
    if stores is not None:
        d["top_stores"] = [store_to_dict(s) for s in stores]
    return d

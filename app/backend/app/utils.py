"""Shared helpers: serialization, geo, opening hours."""
import datetime as dt
import math
from typing import Optional

from .models import Store, Zone

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Store visibility policy: a store is shown to users (and placed on the map)
# only once it has real coordinates. Stores whose location couldn't be geocoded
# are kept in the DB — for manual pinning — but hidden from every user-facing
# store listing until lat/lng are filled in. Spread these expressions into a
# query with `query.filter(*STORE_HAS_COORDS)`; adding coords un-hides a store
# automatically (no flag to flip).
STORE_HAS_COORDS = (Store.lat.isnot(None), Store.lng.isnot(None))


def has_coords(store: Store) -> bool:
    """In-Python equivalent of STORE_HAS_COORDS for already-loaded objects."""
    return store is not None and store.lat is not None and store.lng is not None

# FirstFind is Bengaluru-only; opening hours are always evaluated in IST
# so "open now" is correct regardless of the server's local timezone.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


def sentiment_summary(reviews: list) -> dict:
    """Count reviews by sentiment label. `reviews`: any objects with `.sentiment`.

    Shared by the store detail endpoint and the chatbot so the summary shape
    ({positive, neutral, negative, total}) is defined in exactly one place.
    """
    pos = sum(1 for r in reviews if r.sentiment == "positive")
    neg = sum(1 for r in reviews if r.sentiment == "negative")
    return {"positive": pos, "neutral": len(reviews) - pos - neg,
            "negative": neg, "total": len(reviews)}


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_open_now(store: Store, now: Optional[dt.datetime] = None) -> Optional[bool]:
    """True/False if we have enough info, None if unknown."""
    now = now or now_ist()
    day = DAYS[now.weekday()]
    closed = [d for d in (store.closed_days or "").split(",") if d]
    if day in closed:
        return False
    if not store.open_time or not store.close_time:
        return None
    try:
        o_h, o_m = map(int, store.open_time.split(":"))
        c_h, c_m = map(int, store.close_time.split(":"))
    except ValueError:
        return None
    t = now.hour * 60 + now.minute
    return (o_h * 60 + o_m) <= t <= (c_h * 60 + c_m)


def store_to_dict(store: Store, user_lat=None, user_lng=None) -> dict:
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

"""Distance maths, and the UTC clock the database columns use."""
import datetime as dt
import math


def utcnow() -> dt.datetime:
    """Current UTC time as a naive datetime — how every DateTime column stores
    it. Replaces the deprecated datetime.utcnow()."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

"""Opening hours, always evaluated in IST."""
import datetime as dt
from typing import Optional

from ..models import Store

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# FirstFind is Bengaluru-only; opening hours are always evaluated in IST
# so "open now" is correct regardless of the server's local timezone.
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now_ist() -> dt.datetime:
    return dt.datetime.now(IST)


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

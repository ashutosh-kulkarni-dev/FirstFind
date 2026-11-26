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
    closed = {d.strip().lower() for d in (store.closed_days or "").split(",") if d.strip()}
    if day.lower() in closed:
        return False
    if not store.open_time or not store.close_time:
        return None
    try:
        o_h, o_m = map(int, store.open_time.split(":"))
        c_h, c_m = map(int, store.close_time.split(":"))
    except ValueError:
        return None
    t = now.hour * 60 + now.minute
    opens, closes = o_h * 60 + o_m, c_h * 60 + c_m
    if closes < opens:   # past midnight, e.g. 18:00–01:00
        return t >= opens or t <= closes
    return opens <= t <= closes

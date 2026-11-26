"""Clarifying questions, remembered answers, and trip planning.

The engine calls into this module at three points:

  * before understanding a message — is it an answer to a question we asked?
    (read_answer), and should saved answers be loaded? (load_user_prefs)
  * after understanding it — is the request too vague to answer well?
    (is_vague + slots.next_question -> clarify_result)
  * for "plan a trip" requests — find the start, pick stores, order the walk
    (plan_trip)

Answers are kept in the chat session for the conversation and, for a
logged-in user, saved on the account (User.chat_prefs) for later visits.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Store, User
from ..common.serializers import STORE_HAS_COORDS, store_to_dict
from .contracts import ChatResult, ChatSession, Entities
from .slots import KIND_PHRASE, SKIP, Question, SlotHits, describe, honest_kind, parse_answer

log = logging.getLogger(__name__)

PREF_SLOTS = ("price_tier", "audience", "store_kind")
SEARCH_INTENTS = {"find_by_area", "find_by_category", "find_by_price", "store_recommendation"}
TRIP_RADIUS_KM = 1.2            # stores within an easy walk of the start
TRIP_RADIUS_WIDE_KM = 2.0       # when the first radius finds too few

FORGET_RE = re.compile(r"\b(forget|reset|clear)\b.{0,20}\b(prefs?|preferences|answers|"
                       r"what i (said|told you)|my (budget|choices))\b|^\s*start over\s*$", re.I)


# ---------------------------------------------------------------------------
# Remembered answers
# ---------------------------------------------------------------------------

def load_user_prefs(session: ChatSession, user: Optional[User]) -> None:
    """Apply a logged-in user's saved answers to a new session (once)."""
    if session.prefs_loaded or user is None:
        return
    session.prefs_loaded = True
    try:
        saved = json.loads(user.chat_prefs or "{}")
    except (TypeError, ValueError):
        return
    for slot in PREF_SLOTS:
        if saved.get(slot) and getattr(session.prefs, slot) is None:
            setattr(session.prefs, slot, saved[slot])


def remember(session: ChatSession, db: Session, user: Optional[User], slot: str,
             value: Optional[str]) -> None:
    if slot not in PREF_SLOTS or not value:
        return
    setattr(session.prefs, slot, value)
    _save_user_prefs(db, user, session)


def forget(session: ChatSession, db: Session, user: Optional[User]) -> None:
    for slot in PREF_SLOTS:
        setattr(session.prefs, slot, None)
    session.pending = None
    _save_user_prefs(db, user, session)


def _save_user_prefs(db: Session, user: Optional[User], session: ChatSession) -> None:
    if user is None:
        return
    prefs = session.prefs.remembered()
    user.chat_prefs = json.dumps(prefs) if prefs else None
    try:
        db.commit()
    except Exception:      # noqa: BLE001 — memory is a nicety; never break the reply
        db.rollback()
        log.exception("Could not save chat preferences for user %s", user.id)


# ---------------------------------------------------------------------------
# Answers to a question we asked
# ---------------------------------------------------------------------------

def read_answer(slot: str, msg: str, answer: Optional[dict],
                origin: Optional[tuple[float, float]], db: Session):
    """(is_an_answer, value) for the question on `slot`.

    A tapped option arrives as `answer` ({slot, value}); a typed reply is parsed.
    For "start" the value is {lat, lng, label}; otherwise a slot value or None
    (skipped)."""
    if answer and answer.get("slot") == slot:
        raw = answer.get("value")
        if slot == "start":
            return _start_from(raw, msg, origin, db)
        return True, (None if raw in (None, "", SKIP) else raw)
    if slot == "start":
        return _start_from(None, msg, origin, db)
    return parse_answer(slot, msg)


def _start_from(raw, msg, origin, db):
    if raw == "here":
        if origin:
            return True, {"lat": origin[0], "lng": origin[1], "label": "where you are"}
        return False, None          # location refused: ask again by area
    from .retrieval import understand
    from .geo import resolve_center
    ents = understand(raw or msg, db)
    center = resolve_center(db, ents)
    if center is None:
        return False, None
    label = ents.area or ents.locality or (ents.place.canonical if ents.place else msg.strip())
    return True, {"lat": center[0], "lng": center[1], "label": label}


# ---------------------------------------------------------------------------
# Vague requests
# ---------------------------------------------------------------------------

def is_vague(e: Entities) -> bool:
    """A store search that says at most one thing about what is wanted."""
    if e.store_names:
        return False
    said = sum(bool(x) for x in (
        e.area or e.locality or e.place or e.near_me,
        e.category or e.style,
        e.audience, e.store_kind,
        e.price_tier or e.price_max,
    ))
    return said <= 1


def hits_of(e: Entities) -> SlotHits:
    return SlotHits(store_kind=e.store_kind, audience=e.audience, style=e.style,
                    price_tier=e.price_tier)


def with_answers(e: Entities, session: ChatSession) -> Entities:
    """Fill the request's open slots from this request's answers, then from
    what the user told us earlier."""
    answers = session.pending.answers if session.pending else {}
    fill = {}
    for slot in PREF_SLOTS:
        if getattr(e, slot):
            continue
        if slot in answers:
            fill[slot] = answers[slot]
        elif getattr(session.prefs, slot):
            fill[slot] = getattr(session.prefs, slot)
    return dataclasses.replace(e, **fill) if fill else e


def clarify_result(q: Question, first: bool, extra_options: tuple = ()) -> ChatResult:
    lead = "Happy to help! " if first else ""
    options = [{"label": o.label, "value": o.value} for o in (*q.options, *extra_options)]
    return ChatResult(
        reply=lead + q.text,
        intent="clarify",
        stores=[],
        suggestions=[],
        clarify={"slot": q.slot, "question": q.text, "options": options,
                 "skip": None if q.slot == "start" else "Skip"},
    )


_CITY_NAMES = {"bengaluru", "bangalore", "bengaluru urban"}


def popular_areas(db: Session, n: int = 3) -> list[str]:
    """The neighbourhoods with the most stores (the whole city is not one)."""
    from sqlalchemy import func
    rows = (db.query(Store.area, func.count(Store.id)).filter(*STORE_HAS_COORDS)
            .group_by(Store.area).order_by(func.count(Store.id).desc()).limit(n + 3).all())
    return [a for a, _ in rows if a and a.lower() not in _CITY_NAMES][:n]


# Not worth walking to: rows that name a street or a market, not a shop.
_NOT_A_STOP_RE = re.compile(r"^\W|\bunorganised\b|\bshopping complex\b|\brug shop\b", re.I)


# ---------------------------------------------------------------------------
# Trip planning
# ---------------------------------------------------------------------------

def plan_trip(db: Session, e: Entities, start: dict, prefs) -> ChatResult:
    """Pick a handful of good stores within walking distance of `start` and
    order them into a route, with the nearest metro at each end."""
    from ..ml.clusters import find_cluster
    from .geo import nearest_metro
    from .retrieval import rank_stores
    from .route import plan, route_text

    lat, lng = start["lat"], start["lng"]
    route, by_id = None, {}
    for radius in (TRIP_RADIUS_KM, TRIP_RADIUS_WIDE_KM):
        ids = [s["id"] for s in find_cluster(db, lat, lng, radius).get("stores", [])]
        ranked = rank_stores(db, geo_store_ids=ids, limit=24, prefs=prefs,
                             category=e.category, store_kind=e.store_kind,
                             audience=e.audience, style=e.style, price_tier=e.price_tier)
        stores = [s for s in ranked if not _NOT_A_STOP_RE.search(s.name or "")][:12]
        candidate = plan((lat, lng), start["label"], stores, nearest_metro=nearest_metro,
                         within_km=radius)
        if route is None or len(candidate.stops) > len(route.stops):
            route, by_id = candidate, {s.id: s for s in stores}
        if len(route.stops) >= 3:
            break
    if route is None or not route.stops:
        return ChatResult(
            reply=(f"I couldn't find stores within an easy walk of {start['label']} yet. "
                   "Try another area?"),
            intent="plan_trip", stores=[], suggestions=[f"Plan a trip in {a}" for a in popular_areas(db)])

    ordered = [store_to_dict(by_id[st.id]) for st in route.stops]
    kind = honest_kind(e.store_kind, [by_id[st.id] for st in route.stops])
    what = describe(e.price_tier, e.audience, kind, e.style)
    reply = route_text(route)
    if what != "stores" and len(route.stops) > 1:
        reply = reply.replace(" — about", f" for {what} — about", 1)
    if e.store_kind and not kind:
        reply += f"\n(Not many {KIND_PHRASE[e.store_kind]} stores this close, so I mixed in a few others.)"
    map_spec = {
        "center": [lat, lng], "radius_km": None,
        "stores": [{"id": s["id"], "name": s["name"], "lat": s["lat"], "lng": s["lng"],
                    "is_open_now": s.get("is_open_now")} for s in ordered],
        "metro": route.start_metro,
        "route": [[lat, lng]] + [[st.lat, st.lng] for st in route.stops],
    }
    return ChatResult(
        reply=reply, intent="plan_trip", stores=ordered,
        suggestions=["Only open stores", "Drop the last stop", "Plan a trip somewhere else"],
        map=map_spec,
        action={"type": "open_zones", "label": "Open this area on the full map →",
                "params": {"lat": lat, "lng": lng, "radius_km": TRIP_RADIUS_KM}},
        route=route.to_dict(),
    )

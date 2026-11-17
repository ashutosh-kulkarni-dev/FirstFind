"""THE single composition point for the chat system.

respond(msg, db, user, session_id) is the only function routers call.
It wires the four pillars together; nothing else orchestrates.

Pillar flags (all in config.py):
    CHAT_GEO     — Pillar 1: use geospatial engine (find_cluster + metro)
    CHAT_STATE   — Pillar 2: session memory across turns
    CHAT_TRIPS   — Pillar 3: trip-shaped discovery sets
    CHAT_MAP     — Pillar 4: inline map spec + deep-link action
    CHAT_ADVICE  — Standalone: curated shopping advice intent

Each flag degrades gracefully to today's behaviour when off.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from ..config import (CHAT_ADVICE, CHAT_GEO, CHAT_MAP, CHAT_STATE,
                      CHAT_TRIPS)
from ..ml.llm import phrase_reply
from ..ml.recommender import user_recs
from ..models import Store, User
from ..common.serializers import has_coords, store_to_dict
from .contracts import ChatResult, ChatSession, Draft, Entities, Trip
from .handlers import (GREETING_SUGGESTIONS, SUGGESTIONS, HandlerCtx,
                       dispatch)
from . import assist, slots
from .retrieval import normalize, rank_stores, retrieve, understand

GREETING_RE = re.compile(r"^\s*(hi|hello|hey|yo|namaste|hola)\b", re.I)

# Intents where we always retrieve before dispatching
RETRIEVAL_INTENTS = {"find_by_area", "find_by_category", "find_by_price",
                     "open_now", "store_recommendation"}


def respond(msg: str, db: Session, user: Optional[User] = None,
            session_id: Optional[str] = None,
            origin: Optional[tuple[float, float]] = None,
            answer: Optional[dict] = None) -> dict:
    """Main entry point. Returns a dict matching the ChatResult shape.

    origin: browser-supplied (lat, lng), for "near me" and trip starts.
    answer: a tapped answer to the question we asked last ({slot, value}).
    """

    # ── Greeting short-circuit ──────────────────────────────────────────────
    if GREETING_RE.match(msg) and len(msg.split()) <= 3:
        name = f" {user.name.split()[0]}" if user else ""
        return _serialize(ChatResult(
            reply=(f"Hey{name}! Tell me what you're after — an area, a style, a budget — "
                   "or ask me to plan a thrift walk."),
            intent="general_assistance",
            stores=[],
            suggestions=GREETING_SUGGESTIONS,
        ))

    # ── Pillar 2: load session (and a logged-in user's saved answers) ────────
    session = _load_session(session_id)
    assist.load_user_prefs(session, user)

    if assist.FORGET_RE.search(msg):
        assist.forget(session, db, user)
        _save_session(session_id, session, None, None)
        return _serialize(ChatResult(
            reply="Done — I've forgotten your budget and preferences. What are we looking for?",
            intent="general_assistance", stores=[], suggestions=GREETING_SUGGESTIONS))

    # ── An answer to the question we asked? Then resume that request. ────────
    pending = session.pending
    resumed = False
    if pending is not None:
        slot = pending.asked[-1]
        is_answer, value = assist.read_answer(slot, msg, answer, origin, db)
        if is_answer:
            pending.answers[slot] = value
            assist.remember(session, db, user, slot, value)
            msg, resumed = pending.message, True
        elif slot == "start" and answer and answer.get("value") == "here":
            # Location refused or unavailable: ask for an area instead.
            return _ask(session, session_id, slots.QUESTIONS["start"], db, first=False,
                        reply="No problem — which area are you starting from?")
        else:
            session.pending = pending = None    # a new request instead

    # ── Stage 1: understand ──────────────────────────────────────────────────
    entities = understand(msg, db)
    norm = normalize(msg)
    asked_for = entities                      # what the message itself says
    entities = assist.with_answers(entities, session)

    # ── Trip planning: needs a starting point, then builds a walking route ───
    if entities.intent == "plan_trip":
        return _plan_trip(session, session_id, entities, msg, origin, db)

    # ── Vague store search: ask (at most two) short questions first ──────────
    personal = entities.intent == "store_recommendation" and user and user_recs(db, user.id)
    if entities.intent in assist.SEARCH_INTENTS and assist.is_vague(asked_for) and not personal:
        pending = pending or slots.Pending(message=msg)
        q = slots.next_question(assist.hits_of(asked_for), session.prefs, pending)
        if q is not None:
            pending.asked.append(q.slot)
            session.pending = pending
            return _ask(session, session_id, q, db, first=len(pending.asked) == 1)
    session.pending = None

    # ── Check for trip-refinement ────────────────────────────────────────────
    # Only when the message names nothing new: "vintage under ₹500" or "open
    # now in Jayanagar" after a search is a fresh request, not an edit of the
    # previous trip (it used to be read as "make my trip cheaper").
    if (not resumed and CHAT_TRIPS and CHAT_STATE and session.current_trip
            and session.current_trip.store_ids and not _names_new_subject(asked_for)):
        refine_op = _detect_refine_op(norm)
        if refine_op:
            result = _handle_refinement(refine_op, session, entities, db, user, norm, msg, session_id)
            return _serialize(result)

    # ── Pillar 1: geo-locate ─────────────────────────────────────────────────
    geo_result = None
    if CHAT_GEO:
        from .geo import locate
        geo_result = locate(db, entities, origin=origin)

    geo_store_ids = geo_result.store_ids if geo_result else None

    # ── Handle shopping_advice without retrieval ──────────────────────────────
    if entities.intent == "shopping_advice" and CHAT_ADVICE:
        from .advice import lookup
        tip = lookup(msg)
        result = ChatResult(
            reply=tip,
            intent="shopping_advice",
            stores=[],
            suggestions=SUGGESTIONS[:3],
        )
        _save_session(session_id, session, entities, None)
        return _serialize(result)

    # ── Stage 2+3: retrieve stores + context ─────────────────────────────────
    stores, context = _retrieve_stores(db, entities, user, geo_store_ids, session)

    # ── Stage 4: dispatch to handler ─────────────────────────────────────────
    ctx = HandlerCtx(
        msg=msg, norm=norm, entities=entities,
        stores=stores, context=context, db=db, user=user,
    )
    draft: Draft = dispatch(ctx)

    # ── Pillar 3: build trip ──────────────────────────────────────────────────
    trip: Optional[Trip] = None
    if CHAT_TRIPS and entities.intent in RETRIEVAL_INTENTS and draft.stores:
        from .trip import build as build_trip
        store_dicts = [store_to_dict(s) for s in draft.stores]
        trip = build_trip(store_dicts, geo_result, session.prefs or None)

    # ── Category tip garnish (SHOP) ───────────────────────────────────────────
    if CHAT_ADVICE and entities.category and entities.intent in {"find_by_category", "find_by_area"}:
        from .advice import category_tip
        tip = category_tip(entities.category)
        if tip:
            draft = Draft(reply=draft.reply + f"\n\n💡 {tip}",
                          stores=draft.stores, suggestions=draft.suggestions)

    # ── Stage 5: LLM phrasing ────────────────────────────────────────────────
    reply = phrase_reply(msg, draft.reply, context, entities.intent)

    # ── Pillar 4: map spec ────────────────────────────────────────────────────
    map_spec, action = None, None
    if CHAT_MAP:
        from .mapspec import build as build_map
        map_spec, action = build_map(geo_result, trip, [store_to_dict(s) for s in draft.stores], entities.intent)

    # ── Pillar 2: save session ────────────────────────────────────────────────
    _save_session(session_id, session, entities, trip)

    result = ChatResult(
        reply=reply,
        intent=entities.intent,
        stores=[store_to_dict(s) for s in draft.stores if s],
        suggestions=draft.suggestions or [],
        map=map_spec,
        action=action,
        trip=trip.to_dict() if trip else None,
    )
    return _serialize(result)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _ask(session: ChatSession, session_id: Optional[str], q, db: Session,
         first: bool, reply: Optional[str] = None) -> dict:
    """Return a clarifying question and keep the request waiting for it."""
    extra = ()
    if q.slot == "start":
        extra = tuple(slots.Option(a, a) for a in assist.popular_areas(db))
    result = assist.clarify_result(q, first, extra)
    if reply:
        result.reply = reply
        result.clarify["options"] = [o for o in result.clarify["options"] if o["value"] != "here"]
    _save_session(session_id, session, None, None)
    return _serialize(result)


def _plan_trip(session: ChatSession, session_id: Optional[str], entities: Entities,
               msg: str, origin: Optional[tuple[float, float]], db: Session) -> dict:
    """A walking route from the user's location or a named area; asks where
    to start when the message does not say."""
    pending = session.pending if (session.pending and session.pending.trip) else None
    start = pending.answers.get("start") if pending else None
    if start is None:
        if entities.near_me and origin:
            start = {"lat": origin[0], "lng": origin[1], "label": "where you are"}
        else:
            from .geo import resolve_center
            center = resolve_center(db, entities)
            if center is not None:
                label = (entities.area or entities.locality
                         or (entities.place.canonical if entities.place else "there"))
                start = {"lat": center[0], "lng": center[1], "label": label}
    if start is None:
        session.pending = slots.Pending(message=msg, trip=True, asked=["start"])
        return _ask(session, session_id, slots.QUESTIONS["start"], db, first=True)
    session.pending = None
    result = assist.plan_trip(db, entities, start, session.prefs)
    trip = None
    if result.stores:
        trip = Trip(store_ids=[s["id"] for s in result.stores],
                    center=(start["lat"], start["lng"]), radius_km=assist.TRIP_RADIUS_KM,
                    origin_label=f"{start['label']} thrift walk")
    _save_session(session_id, session, entities, trip)
    return _serialize(result)


def _load_session(session_id: Optional[str]) -> ChatSession:
    if not CHAT_STATE or session_id is None:
        return ChatSession()
    from .state import get_session
    return get_session(session_id)


def _save_session(session_id: Optional[str], session: ChatSession,
                  entities: Optional[Entities], trip: Optional[Trip]) -> None:
    if not CHAT_STATE or session_id is None:
        return
    if entities is not None:
        session.last_entities = entities
    if trip is not None:
        session.current_trip = trip
    from .state import save_session
    save_session(session_id, session)


def _retrieve_stores(db: Session, entities: Entities, user: Optional[User],
                     geo_store_ids: Optional[list[str]],
                     session: ChatSession) -> tuple[list[Store], list[dict]]:
    """Run retrieval, with special handling for recommendation intent."""
    prefs = session.prefs if CHAT_STATE else None

    if entities.intent == "store_recommendation":
        stores = []
        if user:
            rec_ids = user_recs(db, user.id)
            stores = [db.get(Store, sid) for sid in rec_ids]
            stores = [s for s in stores if has_coords(s)][:5]
        if not stores:
            stores = rank_stores(db, area=entities.area, limit=5,
                                 geo_store_ids=geo_store_ids, prefs=prefs,
                                 store_kind=entities.store_kind, audience=entities.audience,
                                 style=entities.style, price_tier=entities.price_tier)
        from .retrieval import _build_context
        return stores, _build_context(db, stores, entities.intent)

    stores, context = retrieve(db, entities, geo_store_ids=geo_store_ids, prefs=prefs)
    return stores, context


REFINE_PATTERNS = [
    ("reorder",   re.compile(r"\b(order|route|sequence|visit order|which (first|next|order)|plan the route)\b")),
    ("open_only", re.compile(r"\b(only open|open ones|open now|currently open|open today)\b")),
    ("cheaper",   re.compile(r"\b(cheaper|less expensive|lower price|more budget|affordable)\b")),
    ("drop",      re.compile(r"\b(drop|remove|exclude|without|not that one|not the last)\b")),
]


def _detect_refine_op(norm: str) -> Optional[str]:
    """Detect trip-refinement intent from normalized text."""
    for op, pattern in REFINE_PATTERNS:
        if pattern.search(norm):
            return op
    return None


def _names_new_subject(e: Entities) -> bool:
    """True when the message itself names a place, store, style or budget."""
    return bool(e.area or e.locality or e.place or e.near_me or e.category or e.style
                or e.store_kind or e.audience or e.price_max or e.store_names)


def _handle_refinement(op: str, session: ChatSession, entities: Entities,
                       db: Session, user: Optional[User], norm: str, msg: str,
                       session_id: Optional[str]) -> ChatResult:
    """Apply a refinement op to the current trip and return a ChatResult."""
    from .trip import refine as refine_trip, itinerary_text

    trip = session.current_trip
    # The current trip's stores (still visible ones) form the candidate pool.
    all_stores = _store_dicts(db, trip.store_ids if trip else [])

    # Also include any newly retrieved stores for add operations
    if entities.area or entities.locality or entities.category:
        extra, _ = retrieve(db, entities)
        all_stores = all_stores + [store_to_dict(s) for s in extra]

    new_trip = refine_trip(trip, op, all_stores, entities)

    op_replies = {
        "cheaper":   "Adjusted — dropped the priciest option and added a cheaper alternative where possible:",
        "open_only": "Filtered to stores likely open right now:",
        "drop":      "Removed the last store from your plan:",
        "reorder":   "Here's the best order to visit these stores:",
    }
    reply_base = op_replies.get(op, "Updated your plan:")

    trip_stores = _store_dicts(db, new_trip.store_ids)

    if op == "reorder":
        itinerary = itinerary_text(new_trip, trip_stores)
        reply_base = reply_base + "\n\n" + itinerary if itinerary else reply_base

    # LLM phrasing
    reply = phrase_reply(msg, reply_base, trip_stores, "plan_refinement")

    # Map spec for the refined trip
    map_spec, action = None, None
    if CHAT_MAP:
        from .mapspec import build as build_map
        map_spec, action = build_map(None, new_trip, trip_stores, "find_by_area")

    # Persist updated trip
    _save_session(session_id, session, entities, new_trip)

    return ChatResult(
        reply=reply,
        intent="plan_refinement",
        stores=trip_stores,
        suggestions=["Show me the route", "Drop the priciest store", "Only open stores"],
        map=map_spec,
        action=action,
        trip=new_trip.to_dict(),
    )


def _store_dicts(db: Session, store_ids: list[str]) -> list[dict]:
    """Serialised stores for these ids, in order, skipping any now hidden."""
    stores = (db.get(Store, sid) for sid in store_ids)
    return [store_to_dict(s) for s in stores if has_coords(s)]


def _serialize(result: ChatResult) -> dict:
    """Convert ChatResult to a plain dict (FastAPI serializes to JSON)."""
    d: dict = {
        "reply":       result.reply,
        "intent":      result.intent,
        "stores":      result.stores,
        "suggestions": result.suggestions,
    }
    # Only include optional fields when they carry data — old clients ignore extras
    if result.map is not None:
        d["map"] = result.map
    if result.action is not None:
        d["action"] = result.action
    if result.trip is not None:
        d["trip"] = result.trip
    if result.clarify is not None:
        d["clarify"] = result.clarify
    if result.route is not None:
        d["route"] = result.route
    return d

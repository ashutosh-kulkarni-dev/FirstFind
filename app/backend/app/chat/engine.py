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
from ..utils import has_coords, store_to_dict
from .contracts import ChatResult, ChatSession, Draft, Entities, Trip
from .handlers import (GREETING_SUGGESTIONS, SUGGESTIONS, HandlerCtx,
                       dispatch)
from .retrieval import normalize, rank_stores, retrieve, understand

GREETING_RE = re.compile(r"^\s*(hi|hello|hey|yo|namaste|hola)\b", re.I)

# Intents where we always retrieve before dispatching
RETRIEVAL_INTENTS = {"find_by_area", "find_by_category", "find_by_price",
                     "open_now", "store_recommendation"}


def respond(msg: str, db: Session, user: Optional[User] = None,
            session_id: Optional[str] = None,
            origin: Optional[tuple[float, float]] = None) -> dict:
    """Main entry point. Returns a dict matching the ChatResult shape.

    origin: browser-supplied (lat, lng), used only when the user says "near me".
    """

    # ── Greeting short-circuit ──────────────────────────────────────────────
    if GREETING_RE.match(msg) and len(msg.split()) <= 3:
        name = f" {user.name.split()[0]}" if user else ""
        return _serialize(ChatResult(
            reply=(f"Hey{name}! I'm the ThriftFind assistant. Ask me anything about "
                   "thrift shopping in Bengaluru — stores by area, category, budget, "
                   "what's open now, or where the best thrift zones are."),
            intent="general_assistance",
            stores=[],
            suggestions=GREETING_SUGGESTIONS,
        ))

    # ── Pillar 2: load session ───────────────────────────────────────────────
    session = _load_session(session_id)

    # ── Stage 1: understand ──────────────────────────────────────────────────
    entities = understand(msg, db)
    norm = normalize(msg)

    # ── Check for trip-refinement ────────────────────────────────────────────
    if CHAT_TRIPS and CHAT_STATE and session.current_trip and session.current_trip.store_ids:
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
        from .advice import lookup, category_tip
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

    # If handler returned the advice sentinel, swap it out
    if draft.reply == "__advice__" and CHAT_ADVICE:
        from .advice import lookup
        draft = Draft(reply=lookup(msg), stores=[], suggestions=SUGGESTIONS[:3])

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

def _load_session(session_id: Optional[str]) -> ChatSession:
    if not CHAT_STATE or session_id is None:
        return ChatSession()
    from .state import get_session
    return get_session(session_id)


def _save_session(session_id: Optional[str], session: ChatSession,
                  entities: Entities, trip: Optional[Trip]) -> None:
    if not CHAT_STATE or session_id is None:
        return
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
                                 geo_store_ids=geo_store_ids, prefs=prefs)
        from .retrieval import _build_context
        return stores, _build_context(db, stores, entities.intent)

    stores, context = retrieve(db, entities, geo_store_ids=geo_store_ids, prefs=prefs)
    return stores, context


def _detect_refine_op(norm: str) -> Optional[str]:
    """Detect trip-refinement intent from normalized text."""
    import re
    REFINE_PATTERNS = [
        ("reorder",   r"\b(order|route|sequence|visit order|which (first|next|order)|plan the route)\b"),
        ("open_only", r"\b(only open|open ones|open now|currently open|open today)\b"),
        ("cheaper",   r"\b(cheaper|less expensive|lower price|more budget|under ₹?\d*|affordable)\b"),
        ("drop",      r"\b(drop|remove|exclude|without|not that one|not the last)\b"),
    ]
    for op, pattern in REFINE_PATTERNS:
        if re.search(pattern, norm):
            return op
    return None


def _handle_refinement(op: str, session: ChatSession, entities: Entities,
                       db: Session, user: Optional[User], norm: str, msg: str,
                       session_id: Optional[str]) -> ChatResult:
    """Apply a refinement op to the current trip and return a ChatResult."""
    from .trip import refine as refine_trip, itinerary_text

    trip = session.current_trip
    # Fetch all stores in the current trip to build the all_stores pool
    from ..models import Store as StoreModel
    all_stores = [store_to_dict(db.get(StoreModel, sid))
                  for sid in (trip.store_ids if trip else [])
                  if db.get(StoreModel, sid)]

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

    # Fetch fresh store dicts for the new trip
    from ..models import Store as StoreModel
    trip_stores = [store_to_dict(db.get(StoreModel, sid))
                   for sid in new_trip.store_ids if db.get(StoreModel, sid)]

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
    return d

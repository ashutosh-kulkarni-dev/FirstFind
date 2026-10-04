"""Intent handler registry — replaces the monolithic if-else in chatbot.py.

Each handler is a small function:
    handler(ctx: HandlerCtx) -> Draft

Adding a new intent = add one entry to HANDLERS. Nothing else changes.

HandlerCtx bundles everything a handler might need (already resolved by the
engine before dispatch) so handlers never do their own DB queries or parsing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..models import Store, User, Zone
from ..utils import is_open_now, now_ist
from .contracts import Draft, Entities
from .retrieval import (get_known_areas, get_store_by_name,
                        get_stores_for_comparison, rank_stores,
                        _sentiment_summary)

SUGGESTIONS = [
    "Show me thrift stores in Koramangala",
    "Vintage stores under ₹500",
    "Which stores are open right now?",
    "Which neighbourhoods have the most thrift stores?",
    "What do people say about the stores in Indiranagar?",
    "Recommend some stores for me",
    "How do I check a thrifted jacket?",
]

GREETING_SUGGESTIONS = [
    "Show me thrift stores in Koramangala",
    "Vintage stores under ₹500",
    "Which stores are open right now?",
    "Where are the best thrift zones?",
]


@dataclass
class HandlerCtx:
    """Everything a handler needs — resolved once by the engine, passed in."""
    msg: str                          # original user message
    norm: str                         # normalized message
    entities: Entities
    stores: list[Store]               # already retrieved + ranked by retrieval.py
    context: list[dict]               # per-store LLM payload
    db: Session
    user: Optional[User]


# ---------------------------------------------------------------------------
# Individual handlers
# ---------------------------------------------------------------------------

def _fmt_score(s: Store) -> str:
    return f"{s.experience_score:.1f}★" if s.experience_score else "unrated"


def _handle_find_by_area(ctx: HandlerCtx) -> Draft:
    place_hit = getattr(ctx.entities, 'place', None)
    near_me = getattr(ctx.entities, 'near_me', False)
    location = (ctx.entities.area or ctx.entities.locality
                or (place_hit.canonical if place_hit else None)
                or ("your location" if near_me else None))
    if ctx.stores:
        n = len(ctx.stores)
        if near_me and not place_hit and not ctx.entities.area:
            reply = f"Found {n} store{'s' if n != 1 else ''} near you."
        else:
            reply = f"Found {n} store{'s' if n != 1 else ''} in {location}."
    else:
        areas = get_known_areas(ctx.db)
        reply = f"I don't have any stores listed in {location or 'that area'} yet."
        return Draft(reply=reply, stores=[], suggestions=[f"Thrift stores in {a}" for a in areas[:3]])
    return Draft(reply=reply, stores=ctx.stores)


def _handle_find_by_category(ctx: HandlerCtx) -> Draft:
    label = ctx.entities.category or "that style"
    _place = getattr(ctx.entities, 'place', None)
    _loc = ctx.entities.area or (_place.canonical if _place else None)
    where = f" in {_loc}" if _loc else ""
    if ctx.stores:
        reply = f"Best matches for {label}{where} first (some stores don't list a style):"
    else:
        reply = f"I couldn't find any {label} stores{where}."
        return Draft(reply=reply, stores=[], suggestions=[f"{c.title()} stores" for c in
                     ["vintage", "streetwear", "denim", "ethnic"] if c != (ctx.entities.category or "")])
    return Draft(reply=reply, stores=ctx.stores)


def _handle_find_by_price(ctx: HandlerCtx) -> Draft:
    price = ctx.entities.price_max or 500
    _place = getattr(ctx.entities, 'place', None)
    _loc = ctx.entities.area or (_place.canonical if _place else None)
    where = f" in {_loc}" if _loc else ""
    if ctx.stores:
        reply = (f"Best picks{where} for a ₹{price} budget — known-cheapest first "
                 "(stores without listed prices are included):")
    else:
        reply = f"I don't have any stores{where} to suggest right now."
    return Draft(reply=reply, stores=ctx.stores)


def _handle_open_now(ctx: HandlerCtx) -> Draft:
    now = now_ist().strftime("%I:%M %p")
    open_ct = sum(1 for s in ctx.stores if is_open_now(s) is True)
    if open_ct:
        reply = f"Likely open right now ({now}), best matches first:"
    else:
        reply = (f"I couldn't confirm anything open at {now} — many stores here "
                 "haven't shared timings. Best options, call before visiting:")
    return Draft(reply=reply, stores=ctx.stores)


def _handle_zone_exploration(ctx: HandlerCtx) -> Draft:
    zones = ctx.db.query(Zone).all()
    if zones:
        lines = [
            f"• {z.label}: {z.store_count} stores within ~{round(z.radius_km, 1) if z.radius_km else '?'} km"
            + (f", avg {z.avg_score}★" if z.avg_score else "")
            for z in zones
        ]
        reply = ("Bengaluru's thrift scene clusters into these neighbourhoods:\n"
                 + "\n".join(lines)
                 + "\nAsk me about any area, or check the Zones page for the map view.")
    else:
        reply = "Zone data isn't computed yet — run the seed script first."
    return Draft(reply=reply, stores=[])


def _handle_store_recommendation(ctx: HandlerCtx) -> Draft:
    if ctx.stores:
        if ctx.user:
            reply = "Based on stores you've viewed and saved, you might like these:"
        else:
            reply = ("You're browsing as a guest, so here are the highest-rated stores overall — "
                     "log in and interact with a few stores to unlock personalized picks.")
    else:
        if ctx.user:
            reply = "You haven't interacted with enough stores yet, so here are the city's best:"
        else:
            reply = "Here are the highest-rated stores:"
    return Draft(reply=reply, stores=ctx.stores)


def _handle_review_insight(ctx: HandlerCtx) -> Draft:
    targets = get_stores_for_comparison(ctx.norm, ctx.db)
    if targets:
        s = targets[0]
        summ = _sentiment_summary(ctx.db, s)
        if summ["total"]:
            tone = ("mostly positive" if summ["positive"] > summ["negative"] * 2
                    else "mixed" if summ["positive"] >= summ["negative"] else "leaning negative")
            reply = (f"**{s.name}** ({s.area}) scores {_fmt_score(s)} from {summ['total']} "
                     f"reviews — sentiment is {tone} "
                     f"({summ['positive']} positive / {summ['neutral']} neutral / {summ['negative']} negative).")
        else:
            reply = f"**{s.name}** has no verified reviews yet."
        return Draft(reply=reply, stores=[s])
    elif ctx.entities.area:
        stores = rank_stores(ctx.db, area=ctx.entities.area, limit=4)
        reply = (f"Best-reviewed stores in {ctx.entities.area}:" if stores
                 else f"I don't have any stores listed in {ctx.entities.area} yet.")
        return Draft(reply=reply, stores=stores)
    return Draft(
        reply="Which store do you want review insights for? Name one and I'll summarise what people say.",
        stores=[],
    )


def _handle_store_comparison(ctx: HandlerCtx) -> Draft:
    targets = get_stores_for_comparison(ctx.norm, ctx.db)
    if len(targets) >= 2:
        a, b = targets[0], targets[1]
        sa, sb = _sentiment_summary(ctx.db, a), _sentiment_summary(ctx.db, b)
        winner = a if (a.experience_score or 0) >= (b.experience_score or 0) else b
        reply = (f"**{a.name}** ({a.area}): {_fmt_score(a)}, {sa['total']} reviews, "
                 f"₹{a.price_min or '?'}–{a.price_max or '?'}\n"
                 f"**{b.name}** ({b.area}): {_fmt_score(b)}, {sb['total']} reviews, "
                 f"₹{b.price_min or '?'}–{b.price_max or '?'}\n"
                 f"On community experience alone, **{winner.name}** edges it.")
        return Draft(reply=reply, stores=[a, b])
    return Draft(
        reply="Name two stores and I'll compare them — e.g. 'compare EcoDhaga and Love Me Twice'.",
        stores=[],
    )


def _handle_best_time(ctx: HandlerCtx) -> Draft:
    s = get_store_by_name(ctx.norm, ctx.db)
    if s and s.open_time:
        reply = (f"**{s.name}** opens at {s.open_time}. Thrift stock is best early — "
                 "weekday mornings right after opening get first pick of new drops; "
                 "weekends after 5pm are the most crowded."
                 + (f" Note: {s.notes}." if s.notes else ""))
        return Draft(reply=reply, stores=[s])
    return Draft(
        reply=("General rule for Bengaluru thrifting: weekday mornings just after opening "
               "(most stores open 11am) for fresh stock and no crowds. Avoid Sunday evenings. "
               "Many stores close Mondays — check the store card before heading out."),
        stores=[],
    )


def _handle_shopping_advice(ctx: HandlerCtx) -> Draft:
    # Delegates to advice.py via engine; returns a sentinel that engine swaps out.
    # This handler is here so the registry is complete; engine calls advice.lookup()
    # directly and bypasses retrieval for this intent.
    return Draft(reply="__advice__", stores=[])


def _handle_general(ctx: HandlerCtx) -> Draft:
    return Draft(
        reply=("I can help you find thrift stores by area, category, or budget, check "
               "what's open now, explore thrift zones, compare stores, and summarise "
               "reviews. Try one of these:"),
        stores=[],
        suggestions=SUGGESTIONS[:3],
    )


# ---------------------------------------------------------------------------
# Registry — the only place intent → handler mapping lives
# ---------------------------------------------------------------------------

HandlerFn = Callable[[HandlerCtx], Draft]

HANDLERS: dict[str, HandlerFn] = {
    "find_by_area":         _handle_find_by_area,
    "find_by_category":     _handle_find_by_category,
    "find_by_price":        _handle_find_by_price,
    "open_now":             _handle_open_now,
    "zone_exploration":     _handle_zone_exploration,
    "store_recommendation": _handle_store_recommendation,
    "review_insight":       _handle_review_insight,
    "store_comparison":     _handle_store_comparison,
    "best_time_to_visit":   _handle_best_time,
    "shopping_advice":      _handle_shopping_advice,
    "general_assistance":   _handle_general,
}


def dispatch(ctx: HandlerCtx) -> Draft:
    handler = HANDLERS.get(ctx.entities.intent, _handle_general)
    return handler(ctx)

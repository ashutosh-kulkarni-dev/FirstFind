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
from ..common.hours import is_open_now, now_ist
from .contracts import Draft, Entities
from .slots import describe, honest_kind
from .retrieval import (get_known_areas, get_store_by_name,
                        get_stores_for_comparison, rank_stores,
                        _sentiment_summary)

SUGGESTIONS = [
    "Thrift stores in Koramangala",
    "Vintage under ₹500",
    "Plan a thrift walk in Indiranagar",
    "What's open right now?",
    "Ethnic wear for women",
    "Recommend some stores for me",
    "How do I check a thrifted jacket?",
]

GREETING_SUGGESTIONS = [
    "Thrift stores in Koramangala",
    "Vintage under ₹500",
    "Plan a thrift walk near me",
    "What's open right now?",
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


def _where(e: Entities) -> tuple[str, bool]:
    """(" in Koramangala" / " near you" / "", has_location)."""
    place = getattr(e, "place", None)
    loc = e.area or e.locality or (place.canonical if place else None)
    if loc:
        return f" in {loc}", True
    if getattr(e, "near_me", False):
        return " near you", True
    return "", False


def _what(e: Entities, stores: Optional[list] = None) -> str:
    """'budget-friendly vintage stores for women' — the store kind only when
    every store shown is of that kind."""
    style = e.style or (e.category if e.category in {"vintage", "streetwear", "ethnic", "denim",
                                                      "formal"} else None)
    kind = honest_kind(e.store_kind, stores) if stores else e.store_kind
    return describe(e.price_tier, e.audience, kind, style)


def _handle_search(ctx: HandlerCtx) -> Draft:
    """Area, style and budget searches: one short, friendly line; the store
    cards carry the details."""
    e = ctx.entities
    where, has_loc = _where(e)
    what = _what(e, ctx.stores)
    under = f" under ₹{e.price_max}" if e.price_max else ""
    if ctx.stores:
        lead = "Good news — here" if len(ctx.stores) >= 3 else "Here"
        return Draft(reply=f"{lead} are {what}{under}{where} you might like.", stores=ctx.stores)
    if has_loc:
        areas = get_known_areas(ctx.db)
        return Draft(reply=f"I don't have {what}{under}{where} yet. Want to try a nearby area?",
                     stores=[], suggestions=[f"Thrift stores in {a}" for a in areas[:3]])
    return Draft(reply=f"I couldn't find {what}{under} yet — try another style or budget?",
                 stores=[], suggestions=["Vintage under ₹500", "Ethnic wear for women",
                                         "Streetwear in Koramangala"])


def _handle_open_now(ctx: HandlerCtx) -> Draft:
    now = now_ist().strftime("%I:%M %p").lstrip("0")
    open_ct = sum(1 for s in ctx.stores if is_open_now(s) is True)
    if open_ct:
        reply = f"These should be open now ({now}) — happy hunting!"
    else:
        reply = (f"I can't confirm anything open at {now} — lots of stores don't list hours, "
                 "so it's worth calling ahead.")
    return Draft(reply=reply, stores=ctx.stores)


def _handle_zone_exploration(ctx: HandlerCtx) -> Draft:
    zones = ctx.db.query(Zone).all()
    if zones:
        lines = [
            f"• {z.label}: {z.store_count} stores within ~{round(z.radius_km, 1) if z.radius_km else '?'} km"
            + (f", avg {z.avg_score}★" if z.avg_score else "")
            for z in zones
        ]
        reply = ("Bengaluru's shopping clusters:\n" + "\n".join(lines)
                 + "\nAsk about any of them, or say \"plan a walk\" there.")
    else:
        reply = "I don't have the neighbourhood map ready yet — try asking about an area."
    return Draft(reply=reply, stores=[])


def _handle_store_recommendation(ctx: HandlerCtx) -> Draft:
    if ctx.stores and ctx.user:
        reply = "Picked for you, based on the stores you've saved and liked."
    elif ctx.stores:
        what = _what(ctx.entities)
        reply = (f"Here are some well-loved {what}. Log in and save a few to get picks made for you."
                 if what != "stores" else
                 "Here are some well-loved spots. Log in and save a few to get picks made for you.")
    else:
        reply = "I don't have picks for that yet — tell me an area or a style?"
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
    return Draft(reply="Which store? Name one and I'll sum up what people say.", stores=[])


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
    return Draft(reply="Name two stores and I'll compare them — like “EcoDhaga vs Love Me Twice”.",
                 stores=[])


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
        reply=("I can find stores by area, style or budget, check what's open, "
               "or plan a walking route. Try one of these:"),
        stores=[],
        suggestions=SUGGESTIONS[:4],
    )


# ---------------------------------------------------------------------------
# Registry — the only place intent → handler mapping lives
# ---------------------------------------------------------------------------

HandlerFn = Callable[[HandlerCtx], Draft]

HANDLERS: dict[str, HandlerFn] = {
    "find_by_area":         _handle_search,
    "find_by_category":     _handle_search,
    "find_by_price":        _handle_search,
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

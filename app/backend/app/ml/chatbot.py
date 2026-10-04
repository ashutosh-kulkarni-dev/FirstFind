"""Conversational retrieval engine — the primary interface of FirstFind.

Token-free retrieval, LLM only for phrasing. Three deterministic stages feed a
rich, grounded context to the LLM (see CHATBOT_RETRIEVAL_PLAN.md):

  1. Understand  — normalize text, detect intent (regex + fuzzy fallback),
                   extract entities (area, category, price, store names).
  2. Retrieve    — HARD filters (area, category, price ceiling, visibility)
                   bound the eligible set; a relevance score only ORDERS it.
                   Open-now and experience_score are ranking signals, never
                   hard filters. No city-wide substitution: an empty eligible
                   set is reported honestly, never padded with off-constraint
                   stores.
  3. Context     — assemble a complete per-store payload (hours, price, contact,
                   sentiment, review snippets) for the LLM.

Stage 4 (phrasing) lives in llm.py and is the only step that spends tokens; the
rule-based draft here is the offline fallback.

Intents: find_by_area, find_by_category, find_by_price, open_now,
zone_exploration, store_recommendation, review_insight, store_comparison,
best_time_to_visit, general_assistance.
"""
import difflib
import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Review, Store, User, Zone
from ..utils import (STORE_HAS_COORDS, has_coords, is_open_now, now_ist,
                     sentiment_summary, store_to_dict)
from .recommender import user_recs

CATEGORY_SYNONYMS = {
    "vintage": ["vintage", "retro", "old school", "y2k"],
    "streetwear": ["streetwear", "street wear", "hoodies", "sneakers", "baggy"],
    "ethnic": ["ethnic", "kurta", "saree", "sari", "traditional"],
    "denim": ["denim", "jeans", "jackets", "jacket"],
    "oversized": ["oversized", "oversize", "baggy fits"],
    "formal": ["formal", "office wear", "blazer", "shirts"],
    "accessories": ["accessories", "bags", "belts", "jewellery", "jewelry"],
    "budget": ["budget", "cheap", "affordable", "under"],
}

INTENT_PATTERNS = [
    ("store_comparison", r"\b(compare|vs\.?|versus|better|which one)\b"),
    ("review_insight", r"\b(review|say about|people say|reputation|feedback|experience at|rating of|rated)\b"),
    ("best_time_to_visit", r"\b(best time|when should i (go|visit)|crowded|rush|timing to visit)\b"),
    ("open_now", r"\b(open now|open right now|currently open|open today|open at|open on)\b"),
    # Price adjectives (budget/cheap/affordable) route to find_by_price, not zone_exploration.
    # Zone intent requires explicit geographic framing: zones, neighbourhood, where, which part.
    ("find_by_price", r"(₹|\brs\.?\s?\d|\bunder\b|\bbudget\b|\bcheap|\baffordable|\bbelow\b|\bless than\b)"),
    ("zone_exploration", r"\b(zones?|area.*(shopping|thrift)|neighbourhoods?|neighborhoods?|where in|market|which part|which area)\b"),
    ("store_recommendation", r"\b(recommend|suggest|for me|personali[sz]ed|what should i|picks)\b"),
    ("find_by_category", None),   # matched via category synonyms
    ("find_by_area", None),       # matched via known area names
]

# Single-word keywords per intent, used by the fuzzy fallback when the strict
# regex above misses a typo/paraphrase ("recomend", "opn", "reveiws").
INTENT_KEYWORDS = {
    "store_comparison": ["compare", "versus", "better"],
    "review_insight": ["review", "reviews", "reputation", "feedback", "rating"],
    "best_time_to_visit": ["crowded", "timing", "busy"],
    "open_now": ["open", "currently"],
    "zone_exploration": ["zone", "zones", "neighbourhood", "neighborhood", "market"],
    "store_recommendation": ["recommend", "suggest", "picks"],
    "find_by_price": ["under", "budget", "cheap", "affordable", "below"],
}

GREETING_RE = re.compile(r"^\s*(hi|hello|hey|yo|namaste|hola)\b", re.I)

SUGGESTIONS = [
    "Show me thrift stores in Koramangala",
    "Vintage stores under ₹500",
    "Which stores are open right now?",
    "Which neighbourhoods have the most thrift stores?",
    "What do people say about the stores in Indiranagar?",
    "Recommend some stores for me",
]

# ---- ranking weights (see plan: quality leans on these once reviews exist) ----
W_QUALITY = 2.0      # experience_score (None until reviews accrue → 0 contribution)
W_CATEGORY = 1.5     # requested category present
W_PRICE = 1.0        # how far under the stated ceiling
W_POPULARITY = 0.3   # review_count confidence
W_OPEN = 1.5         # open-now boost / closed penalty (soft, never a hard filter)


# =========================================================================
# Stage 1 — Understand (token-free)
# =========================================================================

def _normalize(msg: str) -> str:
    """Lowercase, collapse repeats, strip punctuation (keep ₹ and word chars)."""
    s = msg.lower().strip()
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)     # "sooo" -> "soo"
    s = re.sub(r"[^\w\s₹]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _known_areas(db: Session) -> list[str]:
    # Only areas that have at least one visible (geocoded) store.
    return [a[0] for a in
            db.query(Store.area).filter(*STORE_HAS_COORDS).distinct().all() if a[0]]


def _locality_vocab(db: Session) -> list[str]:
    """Return all distinct non-empty locality_raw values for visible stores.

    Used to broaden the searchable vocabulary beyond canonical area names so
    sub-locality phrases ("Tavrekere Road") can trigger find_by_area.
    """
    rows = (db.query(Store.locality_raw)
              .filter(*STORE_HAS_COORDS)
              .filter(Store.locality_raw.isnot(None))
              .distinct().all())
    return [r[0] for r in rows if r[0]]


def _extract_area(norm: str, areas: list[str], cutoff: float = 0.8) -> Optional[str]:
    """Resolve a (possibly misspelled) area mention to a canonical area name.

    1. Exact substring match (fast path).
    2. Fuzzy match: slide word-windows sized to each area name (±1 word) over the
       message and keep the best similarity. Sizing the window to the area's own
       length lets multi-word areas ("Electronic City", "HSR Layout") tolerate
       misspellings too, not just single-word ones ("koramanagla").
    """
    if not areas:
        return None
    for a in areas:
        if a.lower() in norm:
            return a
    tokens = norm.split()
    best_area, best_ratio = None, 0.0
    for a in areas:
        al = a.lower()
        n = len(al.split())
        for size in {max(1, n - 1), n, n + 1}:
            for i in range(len(tokens) - size + 1):
                window = " ".join(tokens[i:i + size])
                r = difflib.SequenceMatcher(None, window, al).ratio()
                if r > best_ratio:
                    best_ratio, best_area = r, a
    return best_area if best_ratio >= cutoff else None


def _extract_locality_phrase(norm: str, db: Session) -> Optional[str]:
    """Return the raw locality phrase from the query if it matches any store's
    locality_raw string (substring or token overlap). Returns the matched phrase
    as typed (not a canonical area name) so Tier-2 retrieval can use it.

    This runs only when _extract_area() returns None — i.e. the query names a
    sub-locality not in the canonical area vocabulary.
    """
    vocab = _locality_vocab(db)
    if not vocab:
        return None
    norm_tokens = set(norm.split())
    best_phrase, best_score = None, 0
    for raw in vocab:
        raw_l = raw.lower()
        # Exact substring: the raw locality text appears verbatim in the query.
        if raw_l in norm:
            return raw
        # Token overlap: count how many tokens from the locality appear in the query.
        raw_tokens = set(t for t in re.split(r"\W+", raw_l) if len(t) > 2)
        overlap = len(raw_tokens & norm_tokens)
        if overlap > best_score:
            best_score, best_phrase = overlap, raw
    # Require at least one meaningful token match (length > 3 avoids "in", "at" noise).
    if best_score >= 1 and best_phrase:
        meaningful = [t for t in re.split(r"\W+", best_phrase.lower()) if len(t) > 3]
        if meaningful and any(t in norm_tokens for t in meaningful):
            return best_phrase
    return None


def _extract_category(norm: str) -> Optional[str]:
    for cat, syns in CATEGORY_SYNONYMS.items():
        if cat == "budget":
            continue
        for s in syns:
            if s in norm:
                return cat
    return None


def _extract_price(norm: str) -> Optional[int]:
    m = re.search(r"(?:₹|rs\.?\s?|under\s+|below\s+|less than\s+)(\d{2,6})", norm)
    return int(m.group(1)) if m else None


def _fuzzy_intent(norm: str) -> Optional[str]:
    """Fallback intent detection: fuzzy-match message tokens against per-intent
    keywords so typos the strict regex misses still resolve."""
    tokens = norm.split()
    best, best_score = None, 0.0
    for intent, kws in INTENT_KEYWORDS.items():
        for kw in kws:
            for t in tokens:
                r = difflib.SequenceMatcher(None, t, kw).ratio()
                if r >= 0.8 and r > best_score:
                    best, best_score = intent, r
    return best


def _detect_intent(norm: str, areas: list[str], db: Optional[Session] = None) -> str:
    for intent, pattern in INTENT_PATTERNS:
        if pattern and re.search(pattern, norm):
            return intent
    fuzzy = _fuzzy_intent(norm)
    if fuzzy:
        return fuzzy
    if _extract_category(norm):
        return "find_by_category"
    if _extract_area(norm, areas):
        return "find_by_area"
    # Tier-2: check whether any sub-locality phrase from locality_raw matches,
    # even though the canonical area vocabulary didn't.
    if db is not None and _extract_locality_phrase(norm, db):
        return "find_by_area"
    return "general_assistance"


def _extract_stores(norm: str, db: Session, limit=2) -> list[Store]:
    hits = []
    visible = db.query(Store).filter(*STORE_HAS_COORDS).all()
    for s in visible:
        if s.name.lower() in norm:
            hits.append(s)
    if not hits:
        # fuzzy on any 2-3 word window
        names = {s.name.lower(): s for s in visible}
        tokens = norm.split()
        for size in (3, 2):
            for i in range(len(tokens) - size + 1):
                window = " ".join(tokens[i:i + size])
                m = difflib.get_close_matches(window, names.keys(), n=1, cutoff=0.8)
                if m and names[m[0]] not in hits:
                    hits.append(names[m[0]])
    return hits[:limit]


# =========================================================================
# Stage 2 — Retrieve: hard filters bound the set, relevance only orders it
# =========================================================================

def _relevance(s: Store, category=None, price_max=None, open_now=False) -> float:
    """Soft relevance score (higher = better). NEVER excludes a store; it only
    orders the already hard-filtered eligible set."""
    score = 0.0
    if s.experience_score is not None:                     # None until reviews exist
        score += W_QUALITY * (s.experience_score / 5.0)
    if category:
        cats = {c for c in (s.categories or "").split(",") if c}
        if category in cats:
            score += W_CATEGORY
    if price_max and s.price_min is not None and s.price_min <= price_max:
        score += W_PRICE * (1.0 - s.price_min / price_max)  # deeper under ceiling ranks higher
    score += W_POPULARITY * (min(s.review_count or 0, 20) / 20.0)
    if open_now:                                            # soft signal, not a filter
        st = is_open_now(s)
        score += W_OPEN if st is True else (-W_OPEN if st is False else 0.0)
    return score


def _soft_excluded(s: Store, category=None, price_max=None) -> bool:
    """A soft barrier excludes a store ONLY when it is *known* to violate the
    constraint. Missing/blank data is never a reason to exclude — an unpriced or
    uncategorised store stays in and is simply ranked without that boost.

      * price: exclude only if the store's cheapest price is known AND above the
        ceiling (its whole range is out of budget). Blank price → keep.
      * category: exclude only if the store lists categories AND the requested
        one isn't among them. Blank categories → keep.
    """
    if price_max is not None and s.price_min is not None and s.price_min > price_max:
        return True
    if category:
        cats = {c for c in (s.categories or "").split(",") if c}
        if cats and category not in cats:
            return True
    return False


def _locality_match(store: Store, phrase: str) -> bool:
    """Return True if the store's locality_raw or area contains the phrase tokens.

    Used by Tier-2 retrieval to match sub-locality phrases ("Tavrekere Road")
    that don't appear in the canonical area vocabulary.
    """
    phrase_l = phrase.lower()
    target = ((store.locality_raw or "") + " " + (store.area or "")).lower()
    if phrase_l in target:
        return True
    phrase_tokens = {t for t in re.split(r"\W+", phrase_l) if len(t) > 3}
    target_tokens = set(re.split(r"\W+", target))
    return bool(phrase_tokens & target_tokens)


def _rank(db: Session, *, area=None, locality_phrase=None, category=None,
          price_max=None, open_now=False, limit=6) -> list[Store]:
    """Two-tier location retrieval; everything else is soft.

    Tier 1 — canonical area (hard DB filter, existing behaviour).
    Tier 2 — locality_raw token match (NEW): when no canonical area resolved,
              filter in-Python against each store's locality_raw + area blob.
              First tier that produces hits wins.

      * HARD: visibility (coordinates) + location tier.
      * SOFT: category and price exclude only *known* violations (see
        _soft_excluded); blanks are kept.
      * RANK: open-now and experience_score are ranking signals only.
    """
    q = db.query(Store).filter(*STORE_HAS_COORDS)
    if area:
        # Tier 1: exact canonical-area match (unchanged behaviour).
        q = q.filter(Store.area == area)
        stores = [s for s in q.all() if not _soft_excluded(s, category, price_max)]
    elif locality_phrase:
        # Tier 2: sub-locality / raw-string match over all visible stores.
        all_visible = [s for s in q.all() if not _soft_excluded(s, category, price_max)]
        stores = [s for s in all_visible if _locality_match(s, locality_phrase)]
    else:
        stores = [s for s in q.all() if not _soft_excluded(s, category, price_max)]
    stores.sort(key=lambda s: _relevance(s, category, price_max, open_now), reverse=True)
    return stores[:limit]


# =========================================================================
# Stage 3 — Assemble context (token-free): full per-store payload for the LLM
# =========================================================================

def _sentiment_summary(db: Session, store: Store) -> dict:
    revs = db.query(Review).filter(Review.store_id == store.id).all()
    return sentiment_summary(revs)


def _review_snippets(db: Session, store_id: str, k=2) -> list[str]:
    revs = (db.query(Review).filter(Review.store_id == store_id)
            .order_by(Review.created_at.desc()).all())
    return [(r.text or "").strip()[:200] for r in revs if (r.text or "").strip()][:k]


def _build_context(db: Session, stores: list[Store], intent: str) -> list[dict]:
    """Compact-but-complete JSON per store — the ONLY facts the LLM may use.
    Review sentiment/snippets are included only where the intent needs them."""
    include_reviews = intent in ("review_insight", "store_comparison", "best_time_to_visit")
    zone_labels = {z.id: z.label for z in db.query(Zone).all()}
    out = []
    for s in stores:
        c = {
            "name": s.name, "area": s.area,
            "categories": [c for c in (s.categories or "").split(",") if c],
            "price_min": s.price_min, "price_max": s.price_max,
            "open_time": s.open_time, "close_time": s.close_time,
            "is_open_now": is_open_now(s),
            "closed_days": [d for d in (s.closed_days or "").split(",") if d],
            "phone": s.phone, "instagram": s.instagram, "notes": s.notes,
            "experience_score": round(s.experience_score, 2) if s.experience_score else None,
            "review_count": s.review_count or 0,
            "zone": zone_labels.get(s.zone_id),
        }
        if include_reviews:
            c["sentiment_summary"] = _sentiment_summary(db, s)
            c["review_snippets"] = _review_snippets(db, s.id)
        # Drop empty fields to keep the payload lean.
        out.append({k: v for k, v in c.items()
                    if v not in (None, [], "") or k == "is_open_now"})
    return out


# =========================================================================
# Orchestration
# =========================================================================

def _fmt_score(s: Store) -> str:
    return f"{s.experience_score:.1f}★" if s.experience_score else "unrated"


def respond(msg: str, db: Session, user: Optional[User] = None) -> dict:
    """Main entry. Returns {reply, intent, stores: [dict], suggestions: [str]}."""
    norm = _normalize(msg)
    areas = _known_areas(db)
    area = _extract_area(norm, areas)
    # Tier-2: resolve sub-locality phrase only when canonical area didn't match.
    locality_phrase = None if area else _extract_locality_phrase(norm, db)
    intent = _detect_intent(norm, areas, db)
    category = _extract_category(norm)
    price = _extract_price(norm)
    stores: list[Store] = []
    suggestions: list[str] = []
    reply = ""

    if GREETING_RE.match(msg) and len(msg.split()) <= 3:
        name = f" {user.name.split()[0]}" if user else ""
        return {
            "reply": f"Hey{name}! I'm the FirstFind assistant. Ask me anything about"
                     "thrift shopping in Bengaluru — stores by area, category, budget, "
                     "what's open now, or where the best thrift zones are.",
            "intent": "general_assistance", "stores": [],
            "suggestions": SUGGESTIONS[:4],
        }

    if intent == "find_by_area" and (area or locality_phrase):
        location_label = area or locality_phrase
        stores = _rank(db, area=area, locality_phrase=locality_phrase,
                       category=category, price_max=price)
        if stores:
            reply = f"Found {len(stores)} store{'s' if len(stores) != 1 else ''} in {location_label}."
        else:
            # Honest empty set — do NOT substitute out-of-area stores.
            reply = f"I don't have any stores listed in {location_label} yet."
            suggestions = [f"Thrift stores in {a}" for a in areas[:3]]

    elif intent == "find_by_category":
        stores = _rank(db, area=area, category=category, price_max=price)
        label = category or "that style"
        where = f" in {area}" if area else ""
        if stores:
            reply = f"Best matches for {label}{where} first (some stores don't list a style):"
        else:
            reply = f"I couldn't find any {label} stores{where}."
            suggestions = [f"{c.title()} stores" for c in list(CATEGORY_SYNONYMS)[:3] if c != "budget"]

    elif intent == "find_by_price":
        price = price or 500
        stores = _rank(db, area=area, category=category, price_max=price)
        where = f" in {area}" if area else ""
        reply = (f"Best picks{where} for a ₹{price} budget — known-cheapest first "
                 "(stores without listed prices are included):"
                 if stores else f"I don't have any stores{where} to suggest right now.")

    elif intent == "open_now":
        # Open-now is a ranking signal, not a hard filter: rank open stores
        # first but never drop stores whose hours are unknown.
        stores = _rank(db, area=area, category=category, price_max=price, open_now=True)
        now = now_ist().strftime("%I:%M %p")
        open_ct = sum(1 for s in stores if is_open_now(s) is True)
        if open_ct:
            reply = f"Likely open right now ({now}), best matches first:"
        else:
            reply = (f"I couldn't confirm anything open at {now} — many stores here "
                     "haven't shared timings. Best options, call before visiting:")

    elif intent == "zone_exploration":
        zones = db.query(Zone).all()
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

    elif intent == "store_recommendation":
        # No hard constraint here, so top-rated is a legitimate result (not a leak).
        if user:
            rec_ids = user_recs(db, user.id)
            stores = [db.get(Store, sid) for sid in rec_ids]
            stores = [s for s in stores if has_coords(s)][:5]
        if stores:
            reply = "Based on stores you've viewed and saved, you might like these:"
        else:
            stores = _rank(db, area=area, limit=5)
            reply = ("You're browsing as a guest, so here are the highest-rated stores overall — "
                     "log in and interact with a few stores to unlock personalized picks."
                     if not user else
                     "You haven't interacted with enough stores yet, so here are the city's best:")

    elif intent == "review_insight":
        targets = _extract_stores(norm, db)
        if targets:
            s = targets[0]
            summ = _sentiment_summary(db, s)
            if summ["total"]:
                tone = ("mostly positive" if summ["positive"] > summ["negative"] * 2
                        else "mixed" if summ["positive"] >= summ["negative"] else "leaning negative")
                reply = (f"**{s.name}** ({s.area}) scores {_fmt_score(s)} from {summ['total']} "
                         f"reviews — sentiment is {tone} "
                         f"({summ['positive']} positive / {summ['neutral']} neutral / {summ['negative']} negative).")
            else:
                reply = f"**{s.name}** has no verified reviews yet."
            stores = [s]
        elif area:
            stores = _rank(db, area=area, limit=4)
            reply = (f"Best-reviewed stores in {area}:" if stores
                     else f"I don't have any stores listed in {area} yet.")
        else:
            reply = "Which store do you want review insights for? Name one and I'll summarise what people say."

    elif intent == "store_comparison":
        targets = _extract_stores(norm, db)
        if len(targets) >= 2:
            a, b = targets[0], targets[1]
            sa, sb = _sentiment_summary(db, a), _sentiment_summary(db, b)
            winner = a if (a.experience_score or 0) >= (b.experience_score or 0) else b
            reply = (f"**{a.name}** ({a.area}): {_fmt_score(a)}, {sa['total']} reviews, "
                     f"₹{a.price_min or '?'}–{a.price_max or '?'}\n"
                     f"**{b.name}** ({b.area}): {_fmt_score(b)}, {sb['total']} reviews, "
                     f"₹{b.price_min or '?'}–{b.price_max or '?'}\n"
                     f"On community experience alone, **{winner.name}** edges it.")
            stores = [a, b]
        else:
            reply = "Name two stores and I'll compare them — e.g. 'compare EcoDhaga and Love Me Twice'."

    elif intent == "best_time_to_visit":
        targets = _extract_stores(norm, db)
        s = targets[0] if targets else None
        if s and s.open_time:
            reply = (f"**{s.name}** opens at {s.open_time}. Thrift stock is best early — "
                     f"weekday mornings right after opening get first pick of new drops; "
                     f"weekends after 5pm are the most crowded."
                     + (f" Note: {s.notes}." if s.notes else ""))
            stores = [s]
        else:
            reply = ("General rule for Bengaluru thrifting: weekday mornings just after opening "
                     "(most stores open 11am) for fresh stock and no crowds. Avoid Sunday evenings. "
                     "Many stores close Mondays — check the store card before heading out.")

    else:  # general_assistance
        reply = ("I can help you find thrift stores by area, category, or budget, check "
                 "what's open now, explore thrift zones, compare stores, and summarise "
                 "reviews. Try one of these:")
        suggestions = SUGGESTIONS[:3]

    stores = [s for s in stores if s]
    store_dicts = [store_to_dict(s) for s in stores]
    # Stage 4 (tokens): Groq rephrases the draft, grounded ONLY in the rich
    # per-store context. No-op (returns `reply`) when GROQ_API_KEY isn't set or
    # the call fails, so the deterministic draft always stands.
    context = _build_context(db, stores, intent)
    from .llm import phrase_reply
    reply = phrase_reply(msg, reply, context, intent)
    return {
        "reply": reply,
        "intent": intent,
        "stores": store_dicts,
        "suggestions": suggestions,
    }

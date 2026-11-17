"""Stage 1–3: understand, retrieve, build context.

Originally the single-file chatbot (since removed), given two clean public entry points:
    understand(msg, db) -> Entities
    retrieve(db, entities, geo_store_ids, prefs) -> (list[Store], list[dict])

No knowledge of state, trips, maps, or LLM. Pure retrieval logic.
"""
from __future__ import annotations

import difflib
import re
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from ..models import Review, Store, Zone
from ..common.serializers import STORE_HAS_COORDS, sentiment_summary
from ..common.hours import is_open_now
from .contracts import Entities
from .slots import (AUDIENCE_WORDS, STORE_KIND_WORDS, STYLE_WORDS, TIER_WORDS,
                    extract as extract_slots, tier_of)

if TYPE_CHECKING:
    from .contracts import Prefs

CATEGORY_SYNONYMS: dict[str, list[str]] = {
    "vintage": ["vintage", "retro", "old school", "y2k"],
    "streetwear": ["streetwear", "street wear", "hoodies", "sneakers", "baggy"],
    "ethnic": ["ethnic", "kurta", "saree", "sari", "traditional"],
    "denim": ["denim", "jeans", "jackets", "jacket"],
    "oversized": ["oversized", "oversize", "baggy fits"],
    "formal": ["formal", "office wear", "blazer", "shirts"],
    "accessories": ["accessories", "bags", "belts", "jewellery", "jewelry"],
}

TRIP_RE = (r"\b(plan (a |my |me a )?(\w+ )?(trip|route|day|outing|walk)|thrift (run|crawl|trip|walk)|"
           r"shopping (trip|route|day|crawl|walk)|walking (route|tour)|itinerary|day out|"
           r"route (for|through|around)|walk(ing)? between)\b")

INTENT_PATTERNS = [
    ("plan_trip",         TRIP_RE),
    ("store_comparison",  r"\b(compare|vs\.?|versus|better|which one)\b"),
    ("review_insight",    r"\b(review|say about|people say|reputation|feedback|experience at|rating of|rated)\b"),
    ("best_time_to_visit", r"\b(best time|when should i (go|visit)|crowded|rush|timing to visit)\b"),
    ("open_now",          r"\b(open now|open right now|currently open|open today|open at|open on)\b"),
    ("find_by_price",     r"(₹|\brs\.?\s?\d|\bunder\b|\bbudget\b|\bcheap|\baffordable|\bbelow\b|\bless than\b)"),
    ("zone_exploration",  r"\b(zones?|area.*(shopping|thrift)|neighbourhoods?|neighborhoods?|where in|market|which part|which area)\b"),
    ("store_recommendation", r"\b(recommend|suggest|for me|personali[sz]ed|what should i|picks)\b"),
    ("shopping_advice",   r"\b(how (do i|to)|tips?|advice|what (to look|should i look)|check|inspect|spot|bargain|negotiate|buy secondhand)\b"),
    ("find_by_category",  None),
    ("find_by_area",      None),
]

INTENT_KEYWORDS: dict[str, list[str]] = {
    "store_comparison":   ["compare", "versus", "better"],
    "review_insight":     ["review", "reviews", "reputation", "feedback", "rating"],
    "best_time_to_visit": ["crowded", "timing", "busy"],
    "open_now":           ["open", "currently"],
    "zone_exploration":   ["zone", "zones", "neighbourhood", "neighborhood", "market"],
    "store_recommendation": ["recommend", "suggest", "picks"],
    "find_by_price":      ["under", "budget", "cheap", "affordable", "below"],
    "shopping_advice":    ["tips", "advice", "inspect", "check", "bargain"],
}

LOCALITY_STOPWORDS = {
    "near", "me", "my", "around", "close", "nearby", "here", "road", "main",
    "cross", "stage", "block", "layout", "nagar", "phase", "sector", "opposite",
    "next", "behind", "area", "street", "circle", "stores", "shop", "shops",
    "show", "find", "get", "best",
}

W_QUALITY    = 2.0
W_CATEGORY   = 1.5
W_PRICE      = 1.0
W_POPULARITY = 0.3
W_OPEN       = 1.5
W_PREF_LIKED = 1.2   # soft boost for liked category
W_TAG        = 1.5   # store carries the style / audience tag asked for
W_TIER       = 1.0   # store is in the price tier asked for
_AUDIENCE_TAGS = {"womenswear", "menswear", "kids"}
_TIER_ORDER = {"budget": 0, "mid": 1, "premium": 2}
W_PREF_DISLIKE = -2.0  # soft penalty for disliked category


# ---------------------------------------------------------------------------
# Stage 1 — Understand
# ---------------------------------------------------------------------------

def has_phrase(text: str, phrase: str, plural: bool = False) -> bool:
    """`phrase` occurs in `text` as whole words (optionally pluralised). Plain
    `in` matched inside longer words ("sari" in "safari", a short store or
    area name inside another word)."""
    if not phrase:
        return False
    tail = r"(?:e?s)?" if plural else ""
    return re.search(rf"(?<!\w){re.escape(phrase)}{tail}(?!\w)", text) is not None


def _normalize(msg: str) -> str:
    s = msg.lower().strip()
    s = re.sub(r"([a-z])\1{2,}", r"\1\1", s)   # "sooo" -> "soo"; numbers stay intact
    s = re.sub(r"[^\w\s₹]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _known_areas(db: Session) -> list[str]:
    return [a[0] for a in
            db.query(Store.area).filter(*STORE_HAS_COORDS).distinct().all() if a[0]]


def _locality_vocab(db: Session) -> list[str]:
    rows = (db.query(Store.locality_raw)
              .filter(*STORE_HAS_COORDS)
              .filter(Store.locality_raw.isnot(None))
              .distinct().all())
    return [r[0] for r in rows if r[0]]


def _extract_area(norm: str, areas: list[str], cutoff: float = 0.8) -> Optional[str]:
    if not areas:
        return None
    for a in areas:
        if has_phrase(norm, a.lower()):
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
    vocab = _locality_vocab(db)
    if not vocab:
        return None
    norm_tokens = set(norm.split())
    best_phrase, best_score = None, 0
    for raw in vocab:
        raw_l = raw.lower()
        # Case 1: full phrase is a substring — strongest signal, keep as-is
        if raw_l in norm:
            return raw
        raw_tokens = {t for t in re.split(r"\W+", raw_l) if len(t) > 2}
        overlap = len(raw_tokens & norm_tokens)
        if overlap > best_score:
            best_score, best_phrase = overlap, raw
    if best_score >= 2 and best_phrase:
        # Case 2: 2+ overlapping tokens — confident enough
        return best_phrase
    if best_score == 1 and best_phrase:
        # Case 3: single overlapping token — only accept if it's a distinctive proper noun
        raw_tokens = {t for t in re.split(r"\W+", best_phrase.lower()) if len(t) > 2}
        overlap_tokens = raw_tokens & norm_tokens
        for tok in overlap_tokens:
            if tok not in LOCALITY_STOPWORDS and len(tok) >= 5:
                return best_phrase
    return None


def _extract_category(norm: str) -> Optional[str]:
    for cat, syns in CATEGORY_SYNONYMS.items():
        if any(has_phrase(norm, s, plural=True) for s in syns):
            return cat
    return None


def _extract_price(norm: str) -> Optional[int]:
    m = re.search(r"(?:₹|rs\.?\s?|under\s+|below\s+|less than\s+)(\d{2,6})", norm)
    return int(m.group(1)) if m else None


def _fuzzy_intent(norm: str) -> Optional[str]:
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
    if db is not None and _extract_locality_phrase(norm, db):
        return "find_by_area"
    return "general_assistance"


def _extract_stores(norm: str, db: Session, limit: int = 2) -> list[Store]:
    hits = []
    visible = db.query(Store).filter(*STORE_HAS_COORDS).all()
    for s in visible:
        if has_phrase(norm, s.name.lower()):
            hits.append(s)
    if not hits:
        names = {s.name.lower(): s for s in visible}
        tokens = norm.split()
        for size in (3, 2):
            for i in range(len(tokens) - size + 1):
                window = " ".join(tokens[i:i + size])
                m = difflib.get_close_matches(window, names.keys(), n=1, cutoff=0.8)
                if m and names[m[0]] not in hits:
                    hits.append(names[m[0]])
    return hits[:limit]


_NEAR_ME_RE = re.compile(
    r"\b(near me|close to me|around me|nearby|my location|current location|around here|near here)\b"
)


_BROWSE_RE = re.compile(r"\b(stores?|shops?|shopping|clothes|clothing|outfits?|something to wear|"
                        r"places to (shop|buy))\b")
_NOT_PLACE_RE = re.compile(
    "|".join([*STORE_KIND_WORDS.values(), *AUDIENCE_WORDS.values(), *STYLE_WORDS.values(),
              *TIER_WORDS.values(),
              r"\b(under|below|less than|upto|up to)\s*₹?\s*\d+\b", r"₹\s*\d+", r"\b\d+\b",
              r"\b(show|find|me|some|any|the|a|an|stores?|shops?|shopping|for|please|good|"
              r"best|nice|want|looking|need|buy|clothes|clothing|outfits?|something|wear|"
              r"budget|mid|range|premium|kids?|skip|in|at|near|around|from|plan|trip|walk|"
              r"walking|route|run|crawl|day|out|outing|itinerary|starting|start)\b"]))


def _without_slot_words(norm: str) -> str:
    """The message minus shopping words and prices — what might name a place."""
    return re.sub(r"\s+", " ", _NOT_PLACE_RE.sub(" ", norm)).strip()


def understand(msg: str, db: Session) -> Entities:
    """Stage 1 — pure extraction. Returns Entities with no DB writes."""
    from .places import resolve_place
    norm = _normalize(msg)
    price_max = _extract_price(norm)
    slots = extract_slots(norm, price_max)
    # Words about who / what / how much ("women", "budget", "under 700") are
    # not places: look for the location in what is left.
    where = _without_slot_words(norm)
    areas = _known_areas(db)
    area = _extract_area(where, areas) if where else None
    near_me = bool(_NEAR_ME_RE.search(norm))
    # Precedence: store-area exact > tightened locality fuzzy > gazetteer
    locality = None if (area or not where) else _extract_locality_phrase(where, db)
    place = None
    if where and not area and not locality and not near_me:
        place = resolve_place(where)
    intent = _detect_intent(norm, areas, db)
    # "Brand stores for men", "show me some stores": a store search even
    # without an area or a known category.
    if intent == "general_assistance" and (slots.store_kind or slots.audience or slots.style
                                           or slots.price_tier or _BROWSE_RE.search(norm)):
        intent = "find_by_category"
    # Gazetteer hit forces find_by_area if intent wasn't already geographic
    if place and intent not in {"find_by_area", "find_by_category", "find_by_price",
                                "open_now", "store_recommendation", "zone_exploration",
                                "plan_trip"}:
        intent = "find_by_area"
    if near_me and intent == "general_assistance":
        intent = "find_by_area"
    named = _extract_stores(norm, db)
    if intent in {"find_by_area", "find_by_category", "find_by_price", "store_recommendation",
                  "plan_trip"}:
        # In a search, only a store named in full counts: fuzzy windows turn
        # "me stores" into "Re Store".
        named = [s for s in named if has_phrase(norm, s.name.lower())]
    return Entities(
        intent=intent,
        area=area,
        locality=locality,
        category=_extract_category(norm),
        price_max=price_max,
        store_names=[s.name for s in named],
        open_now=(intent == "open_now"),
        place=place,
        near_me=near_me,
        store_kind=slots.store_kind,
        audience=slots.audience,
        style=slots.style,
        price_tier=slots.price_tier,
    )


# ---------------------------------------------------------------------------
# Stage 2 — Retrieve
# ---------------------------------------------------------------------------

def _relevance(s: Store, category: Optional[str], price_max: Optional[int],
               open_now: bool, prefs: Optional[Prefs], tags: tuple = (),
               price_tier: Optional[str] = None) -> float:
    score = 0.0
    if tags:
        own = {t for t in (s.tags or "").split(",") if t}
        score += W_TAG * len(own & set(tags))
    if price_tier and tier_of(s) == price_tier:
        score += W_TIER
    if s.experience_score is not None:
        score += W_QUALITY * (s.experience_score / 5.0)
    if category:
        cats = {c for c in (s.categories or "").split(",") if c}
        if category in cats:
            score += W_CATEGORY
    if price_max and s.price_min is not None and s.price_min <= price_max:
        score += W_PRICE * (1.0 - s.price_min / price_max)
    score += W_POPULARITY * (min(s.review_count or 0, 20) / 20.0)
    if open_now:
        st = is_open_now(s)
        score += W_OPEN if st is True else (-W_OPEN if st is False else 0.0)
    if prefs:
        s_cats = {c for c in (s.categories or "").split(",") if c}
        for liked in prefs.liked_categories:
            if liked in s_cats:
                score += W_PREF_LIKED
        for disliked in prefs.disliked_categories:
            if disliked in s_cats:
                score += W_PREF_DISLIKE
        if (prefs.budget_ceiling and price_max is None and s.price_min is not None
                and s.price_min <= prefs.budget_ceiling):
            score += W_PRICE * 0.5
    return score


def _soft_excluded(s: Store, category: Optional[str], price_max: Optional[int],
                   audience: Optional[str] = None, price_tier: Optional[str] = None) -> bool:
    if price_max is not None and s.price_min is not None and s.price_min > price_max:
        return True
    if audience:
        # A store tagged only for someone else (a kids' shop when you want
        # menswear) is out; untagged stores stay in.
        own = {t for t in (s.tags or "").split(",") if t} & _AUDIENCE_TAGS
        if own and audience not in own:
            return True
    if price_tier:
        tier = tier_of(s)
        if tier and abs(_TIER_ORDER[tier] - _TIER_ORDER[price_tier]) > 1:
            return True
    if category:
        cats = {c for c in (s.categories or "").split(",") if c}
        if cats and category not in cats:
            return True
    return False


def _locality_match(store: Store, phrase: str) -> bool:
    phrase_l = phrase.lower()
    target = ((store.locality_raw or "") + " " + (store.area or "")).lower()
    if phrase_l in target:
        return True
    phrase_tokens = {t for t in re.split(r"\W+", phrase_l) if len(t) > 3}
    return bool(phrase_tokens & set(re.split(r"\W+", target)))


def rank_stores(db: Session, *, area: Optional[str] = None,
                locality_phrase: Optional[str] = None,
                category: Optional[str] = None, price_max: Optional[int] = None,
                open_now: bool = False, limit: int = 6,
                geo_store_ids: Optional[list[str]] = None,
                prefs: Optional[Prefs] = None,
                store_kind: Optional[str] = None, audience: Optional[str] = None,
                style: Optional[str] = None, price_tier: Optional[str] = None) -> list[Store]:
    """Two-tier location retrieval with optional geo + prefs boosting.

    When geo_store_ids is provided (Pillar 1), those stores are ranked first
    (they are the geospatially-coherent set). The string-match path is the
    fallback when Pillar 1 is off.
    """
    q = db.query(Store).filter(*STORE_HAS_COORDS)

    def excluded(s: Store) -> bool:
        return _soft_excluded(s, category, price_max, audience, price_tier)

    tags = tuple(t for t in (audience, style) if t)

    if geo_store_ids is not None:
        # Pillar 1 path: geo engine already filtered; we just rank + soft-filter.
        # If the user explicitly named an area, intersect — a radius query around
        # one area's centroid otherwise spills into neighboring areas (e.g. a
        # Koramangala search returning S G Palya because its stores sit inside
        # Koramangala's search radius).
        id_set = set(geo_store_ids)
        stores = [s for s in q.all()
                  if s.id in id_set and not excluded(s)
                  and (not area or s.area == area)]
    elif area:
        stores = [s for s in q.filter(Store.area == area).all()
                  if not excluded(s)]
    elif locality_phrase:
        all_visible = [s for s in q.all() if not excluded(s)]
        stores = [s for s in all_visible if _locality_match(s, locality_phrase)]
    else:
        stores = [s for s in q.all() if not excluded(s)]

    if store_kind:
        # A named kind is a filter, unless it would leave almost nothing
        # (then the closest other stores are better than an empty answer).
        of_kind = [s for s in stores if (s.store_type or "thrift") == store_kind]
        if len(of_kind) >= min(3, limit):
            stores = of_kind
    # Stores of the kind asked for always come before the others mixed in.
    stores.sort(key=lambda s: (bool(store_kind) and (s.store_type or "thrift") == store_kind,
                               _relevance(s, category, price_max, open_now, prefs, tags, price_tier)),
                reverse=True)
    return stores[:limit]


def retrieve(db: Session, entities: Entities,
             geo_store_ids: Optional[list[str]] = None,
             prefs: Optional[Prefs] = None) -> tuple[list[Store], list[dict]]:
    """Stage 2+3: retrieve matching stores and build their context payload."""
    stores = rank_stores(
        db,
        area=entities.area,
        locality_phrase=entities.locality,
        category=entities.category,
        price_max=entities.price_max,
        open_now=entities.open_now,
        geo_store_ids=geo_store_ids,
        prefs=prefs,
        store_kind=entities.store_kind,
        audience=entities.audience,
        style=entities.style,
        price_tier=entities.price_tier,
    )
    context = _build_context(db, stores, entities.intent)
    return stores, context


# ---------------------------------------------------------------------------
# Stage 3 — Build context
# ---------------------------------------------------------------------------

def _sentiment_summary(db: Session, store: Store) -> dict:
    revs = db.query(Review).filter(Review.store_id == store.id).all()
    return sentiment_summary(revs)


def _review_snippets(db: Session, store_id: str, k: int = 2) -> list[str]:
    revs = (db.query(Review).filter(Review.store_id == store_id)
            .order_by(Review.created_at.desc()).all())
    return [(r.text or "").strip()[:200] for r in revs if (r.text or "").strip()][:k]


def _build_context(db: Session, stores: list[Store], intent: str) -> list[dict]:
    """Compact per-store payload for the LLM — the only facts it may use."""
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
        out.append({k: v for k, v in c.items()
                    if v not in (None, [], "") or k == "is_open_now"})
    return out


def get_store_by_name(norm: str, db: Session) -> Optional[Store]:
    """Convenience for handlers that need a single named store."""
    hits = _extract_stores(norm, db, limit=1)
    return hits[0] if hits else None


def get_stores_for_comparison(norm: str, db: Session) -> list[Store]:
    return _extract_stores(norm, db, limit=2)


def get_known_areas(db: Session) -> list[str]:
    return _known_areas(db)


def normalize(msg: str) -> str:
    return _normalize(msg)

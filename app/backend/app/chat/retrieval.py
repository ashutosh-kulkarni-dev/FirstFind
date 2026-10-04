"""Stage 1–3: understand, retrieve, build context.

Lifted from ml/chatbot.py and given two clean public entry points:
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
from ..utils import (STORE_HAS_COORDS, has_coords, is_open_now, now_ist,
                     sentiment_summary, store_to_dict)
from .contracts import Entities

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
    "budget": ["budget", "cheap", "affordable", "under"],
}

INTENT_PATTERNS = [
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

REFINE_PATTERNS = [
    ("cheaper",    r"\b(cheaper|less expensive|lower price|budget|under ₹?\d*)\b"),
    ("open_only",  r"\b(only open|open ones|open now|currently open)\b"),
    ("add_area",   r"\b(add|include|also|and)\b.{0,20}\b(area|stores?|shops?)\b"),
    ("drop",       r"\b(drop|remove|exclude|not|without)\b"),
    ("reorder",    r"\b(order|route|sequence|visit order|which (first|order))\b"),
]

GREETING_RE = re.compile(r"^\s*(hi|hello|hey|yo|namaste|hola)\b", re.I)

W_QUALITY    = 2.0
W_CATEGORY   = 1.5
W_PRICE      = 1.0
W_POPULARITY = 0.3
W_OPEN       = 1.5
W_PREF_LIKED = 1.2   # soft boost for liked category
W_PREF_DISLIKE = -2.0  # soft penalty for disliked category


# ---------------------------------------------------------------------------
# Stage 1 — Understand
# ---------------------------------------------------------------------------

def _normalize(msg: str) -> str:
    s = msg.lower().strip()
    s = re.sub(r"(.)\1{2,}", r"\1\1", s)
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
        raw_tokens = set(t for t in re.split(r"\W+", raw_l) if len(t) > 2)
        overlap = len(raw_tokens & norm_tokens)
        if overlap > best_score:
            best_score, best_phrase = overlap, raw
    if best_score >= 2 and best_phrase:
        # Case 2: 2+ overlapping tokens — confident enough
        return best_phrase
    if best_score == 1 and best_phrase:
        # Case 3: single overlapping token — only accept if it's a distinctive proper noun
        raw_tokens = set(t for t in re.split(r"\W+", best_phrase.lower()) if len(t) > 2)
        overlap_tokens = raw_tokens & norm_tokens
        for tok in overlap_tokens:
            if tok not in LOCALITY_STOPWORDS and len(tok) >= 5:
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


def _detect_refine_op(norm: str) -> Optional[str]:
    """Detect if this message is a trip-refinement rather than a new query."""
    for op, pattern in REFINE_PATTERNS:
        if re.search(pattern, norm):
            return op
    return None


def _extract_stores(norm: str, db: Session, limit: int = 2) -> list[Store]:
    hits = []
    visible = db.query(Store).filter(*STORE_HAS_COORDS).all()
    for s in visible:
        if s.name.lower() in norm:
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


def understand(msg: str, db: Session) -> Entities:
    """Stage 1 — pure extraction. Returns Entities with no DB writes."""
    from .places import resolve_place
    norm = _normalize(msg)
    areas = _known_areas(db)
    area = _extract_area(norm, areas)
    near_me = bool(_NEAR_ME_RE.search(norm))
    # Precedence: store-area exact > tightened locality fuzzy > gazetteer
    locality = None if area else _extract_locality_phrase(norm, db)
    place = None
    if not area and not locality and not near_me:
        place = resolve_place(norm)
    intent = _detect_intent(norm, areas, db)
    # Gazetteer hit forces find_by_area if intent wasn't already geographic
    if place and intent not in {"find_by_area", "find_by_category", "find_by_price",
                                "open_now", "store_recommendation", "zone_exploration"}:
        intent = "find_by_area"
    if near_me and intent == "general_assistance":
        intent = "find_by_area"
    return Entities(
        intent=intent,
        area=area,
        locality=locality,
        category=_extract_category(norm),
        price_max=_extract_price(norm),
        store_names=[s.name for s in _extract_stores(norm, db)],
        open_now=(intent == "open_now"),
        place=place,
        near_me=near_me,
    )


# ---------------------------------------------------------------------------
# Stage 2 — Retrieve
# ---------------------------------------------------------------------------

def _relevance(s: Store, category: Optional[str], price_max: Optional[int],
               open_now: bool, prefs: Optional[Prefs]) -> float:
    score = 0.0
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
        if prefs.budget_ceiling and price_max is None and s.price_min is not None:
            if s.price_min <= prefs.budget_ceiling:
                score += W_PRICE * 0.5
    return score


def _soft_excluded(s: Store, category: Optional[str], price_max: Optional[int]) -> bool:
    if price_max is not None and s.price_min is not None and s.price_min > price_max:
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
                prefs: Optional[Prefs] = None) -> list[Store]:
    """Two-tier location retrieval with optional geo + prefs boosting.

    When geo_store_ids is provided (Pillar 1), those stores are ranked first
    (they are the geospatially-coherent set). The string-match path is the
    fallback when Pillar 1 is off.
    """
    q = db.query(Store).filter(*STORE_HAS_COORDS)

    if geo_store_ids is not None:
        # Pillar 1 path: geo engine already filtered; we just rank + soft-filter
        id_set = set(geo_store_ids)
        stores = [s for s in q.all()
                  if s.id in id_set and not _soft_excluded(s, category, price_max)]
    elif area:
        stores = [s for s in q.filter(Store.area == area).all()
                  if not _soft_excluded(s, category, price_max)]
    elif locality_phrase:
        all_visible = [s for s in q.all() if not _soft_excluded(s, category, price_max)]
        stores = [s for s in all_visible if _locality_match(s, locality_phrase)]
    else:
        stores = [s for s in q.all() if not _soft_excluded(s, category, price_max)]

    stores.sort(key=lambda s: _relevance(s, category, price_max, open_now, prefs),
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

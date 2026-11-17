"""Shopping slots: store kind, tags, price tier and who it's for.

    extract(norm) -> SlotHits      what the message itself says
    tier_of(store) -> str | None   a store's price tier
    QUESTIONS / next_question()    the clarifying questions and their answers
    parse_answer(slot, text)       a typed or tapped answer -> slot value

Pure functions over text and Store rows. Imports nothing from chat/ except
contracts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .contracts import Prefs

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

STORE_KIND_WORDS = {
    "thrift": r"\bthrift\w*|\bsecond[- ]?hand\b|\bpre[- ]?loved\b|\bpre[- ]?owned\b|\bused clothes\b",
    "retail_fashion": r"\bboutiques?\b|\blocal (stores?|shops?|brands?)\b|\bdesigner\b",
    "branded": r"\bbrand(ed)? (stores?|shops?)\b|\bbig brands?\b|\bmall\b|\bbrands\b",
    "factory_outlet": r"\bfactory outlets?\b|\boutlets?\b|\bsurplus\b|\bexport surplus\b",
}

# Who it's for -> tag. Checked before the style tags.
AUDIENCE_WORDS = {
    "womenswear": (r"\bwomen'?s?\b|\bwomens?wear\b|\bladies\b|\bgirls?\b|\bfor (her|my (wife|mom|mum|"
                   r"mother|sister|girlfriend))\b|\bgirlfriend\b|\bwife\b"),
    "menswear": (r"\bmen'?s?\b|\bmens?wear\b|\bguys?\b|\bgents?\b|\bfor (him|my (husband|dad|father|"
                 r"brother|boyfriend))\b|\bboyfriend\b|\bhusband\b"),
    "kids": r"\bkids?\b|\bchild(ren)?\b|\bbaby\b|\btoddlers?\b|\bfor my (son|daughter|kid)\b",
}

STYLE_WORDS = {
    "vintage": r"\bvintage\b|\bretro\b|\by2k\b|\b90s\b|\bold[- ]school\b",
    "streetwear": r"\bstreet ?wear\b|\bhoodies?\b|\bsneakers?\b|\bbaggy\b|\boversized?\b",
    "ethnic": r"\bethnic\b|\bkurtas?\b|\bkurtis?\b|\bsarees?\b|\bsaris?\b|\btraditional\b|\blehengas?\b",
    "denim": r"\bdenims?\b|\bjeans\b",
    "formal": r"\bformals?\b|\boffice ?wear\b|\bblazers?\b|\bsuits?\b|\bwork clothes\b",
    "sportswear": r"\bsports? ?wear\b|\bgym\b|\bathleisure\b|\brunning\b|\bactivewear\b",
    "bridal": r"\bbridal\b|\bwedding\b|\bbride\b",
}

TIER_WORDS = {
    "budget": r"\bbudget\b|\bcheap\w*\b|\baffordable\b|\binexpensive\b|\blow[- ]cost\b|\bpocket[- ]friendly\b",
    "mid": r"\bmid[- ]?range\b|\bmoderate\w*\b|\bmid[- ]priced\b|\breasonabl[ey]\b",
    "premium": r"\bpremium\b|\bluxury\b|\bhigh[- ]end\b|\bsplurge\b|\bexpensive\b|\bdesigner\b",
}

TIER_LIMITS = {"budget": 700, "mid": 2000}   # midpoint price ₹ below which a store is in the tier

_KIND_RES = {k: re.compile(v) for k, v in STORE_KIND_WORDS.items()}
_AUDIENCE_RES = {k: re.compile(v) for k, v in AUDIENCE_WORDS.items()}
_STYLE_RES = {k: re.compile(v) for k, v in STYLE_WORDS.items()}
_TIER_RES = {k: re.compile(v) for k, v in TIER_WORDS.items()}


@dataclass(frozen=True)
class SlotHits:
    store_kind: Optional[str] = None
    audience: Optional[str] = None        # a tag: womenswear / menswear / kids
    style: Optional[str] = None           # a tag: vintage / ethnic / ...
    price_tier: Optional[str] = None      # budget / mid / premium


def tier_for_price(price: int) -> str:
    return "budget" if price < TIER_LIMITS["budget"] else "mid" if price < TIER_LIMITS["mid"] else "premium"


def extract(norm: str, price_max: Optional[int] = None) -> SlotHits:
    """Slots stated in a normalised (lower-case) message."""
    def first(res: dict) -> Optional[str]:
        return next((k for k, rx in res.items() if rx.search(norm)), None)
    tier = first(_TIER_RES)
    if tier is None and price_max:
        tier = tier_for_price(price_max - 1)   # "under 2000" is mid-range, not premium
    return SlotHits(store_kind=first(_KIND_RES), audience=first(_AUDIENCE_RES),
                    style=first(_STYLE_RES), price_tier=tier)


def tier_of(store) -> Optional[str]:
    """A store's price tier from its own prices; None when the prices are only
    a generic estimate for its kind (thrift shops are then taken as budget)."""
    if getattr(store, "price_estimated", False) or (store.price_min is None and store.price_max is None):
        return "budget" if (store.store_type or "thrift") in ("thrift", "factory_outlet") else None
    lo, hi = store.price_min, store.price_max
    mid = ((lo or hi) + (hi or lo)) / 2
    return tier_for_price(int(mid))


# ---------------------------------------------------------------------------
# Clarifying questions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Option:
    label: str
    value: str


@dataclass(frozen=True)
class Question:
    slot: str
    text: str
    options: tuple[Option, ...]


SKIP = "skip"

QUESTIONS = {
    "price_tier": Question("price_tier", "What budget are you thinking?", (
        Option("Budget · under ₹700", "budget"),
        Option("Mid-range · ₹700–2,000", "mid"),
        Option("Premium · ₹2,000+", "premium"),
    )),
    "audience": Question("audience", "Who's it for?", (
        Option("Women", "womenswear"),
        Option("Men", "menswear"),
        Option("Kids", "kids"),
    )),
    "store_kind": Question("store_kind", "Any kind of store in mind?", (
        Option("Thrift & pre-loved", "thrift"),
        Option("Local boutiques", "retail_fashion"),
        Option("Brand stores", "branded"),
    )),
    "start": Question("start", "Where are you starting from?", (
        Option("📍 Use my location", "here"),
    )),
}

MAX_QUESTIONS = 2


@dataclass
class Pending:
    """A request waiting on clarifying answers (kept in the chat session)."""
    message: str
    asked: list[str] = field(default_factory=list)
    answers: dict[str, Optional[str]] = field(default_factory=dict)
    trip: bool = False


def known(slot: str, hits: SlotHits, prefs: Prefs, answers: dict) -> bool:
    if slot in answers:
        return True            # answered or skipped
    if slot == "price_tier":
        return bool(hits.price_tier or prefs.price_tier)
    if slot == "audience":
        return bool(hits.audience or prefs.audience)
    if slot == "store_kind":
        return bool(hits.store_kind or prefs.store_kind)
    return False


def next_question(hits: SlotHits, prefs: Prefs, pending: Pending) -> Optional[Question]:
    """The next clarifying question for a vague request, or None to go ahead.

    hits: what the message itself says. Budget first, then who it's for — or,
    when the message already says who, the store kind. Anything remembered
    from earlier counts as answered, so a returning user is asked nothing."""
    if len(pending.asked) >= MAX_QUESTIONS:
        return None
    if not known("price_tier", hits, prefs, pending.answers):
        return QUESTIONS["price_tier"]
    if not known("audience", hits, prefs, pending.answers):
        return QUESTIONS["audience"]
    if hits.audience and not known("store_kind", hits, prefs, pending.answers):
        return QUESTIONS["store_kind"]
    return None


_SKIP_RE = re.compile(r"^\s*(skip|any|anything|anyone|no preference|doesn'?t matter|not sure|whatever|"
                      r"all|everyone|no idea|either)\s*[.!]?\s*$", re.I)


def parse_answer(slot: str, text: str) -> tuple[bool, Optional[str]]:
    """(is_an_answer, value). value None means skipped. A message that is not
    an answer to `slot` returns (False, None) so it is treated as a new request."""
    t = (text or "").strip().lower()
    if _SKIP_RE.match(t):
        return True, None
    q = QUESTIONS.get(slot)
    if q:
        for opt in q.options:
            if t == opt.label.lower() or t == opt.value:
                return True, opt.value
    hits = extract(t, _price_in(t))
    value = {"price_tier": hits.price_tier, "audience": hits.audience,
             "store_kind": hits.store_kind}.get(slot)
    if value:
        return True, value
    if slot == "price_tier":
        for word, tier in (("mid", "mid"), ("low", "budget"), ("high", "premium")):
            if re.search(rf"\b{word}\b", t):
                return True, tier
    return False, None


def _price_in(text: str) -> Optional[int]:
    m = re.search(r"(\d[\d,]{1,6})", text)
    return int(m.group(1).replace(",", "")) if m else None


# ---------------------------------------------------------------------------
# Words for replies
# ---------------------------------------------------------------------------

TIER_PHRASE = {"budget": "budget-friendly", "mid": "mid-range", "premium": "premium"}
AUDIENCE_PHRASE = {"womenswear": "for women", "menswear": "for men", "kids": "for kids"}
KIND_PHRASE = {"thrift": "thrift", "retail_fashion": "boutique", "branded": "brand",
               "factory_outlet": "factory outlet"}
STYLE_PHRASE = {"vintage": "vintage", "streetwear": "streetwear", "ethnic": "ethnic",
                "denim": "denim", "formal": "formal", "sportswear": "sportswear", "bridal": "bridal"}


def describe(tier: Optional[str], audience: Optional[str], kind: Optional[str],
             style: Optional[str]) -> str:
    """'budget-friendly vintage thrift stores for women'."""
    words = [TIER_PHRASE.get(tier or ""), STYLE_PHRASE.get(style or ""), KIND_PHRASE.get(kind or "")]
    text = " ".join(w for w in words if w)
    text = f"{text} stores" if text else "stores"
    if audience:
        text += f" {AUDIENCE_PHRASE[audience]}"
    return text


def honest_kind(kind: Optional[str], stores: list) -> Optional[str]:
    """The store kind to name in a reply: only if every store shown is of it
    (the search falls back to other kinds when too few match)."""
    if kind and stores and all((s.store_type or "thrift") == kind for s in stores):
        return kind
    return None

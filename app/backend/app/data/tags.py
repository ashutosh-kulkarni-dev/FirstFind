"""Store tags: who a store is for and what it mainly sells.

Tags come from plain keyword rules — no model, nothing guessed beyond what
the text says:

  1. the store's own name, Google type and description (one mention is enough);
  2. its reviews (two mentions needed, since a single review is weak evidence);
  3. a short table of well-known chains whose range is common knowledge.

Many small shops say nothing about their range, so they get no tags. That is
honest: an untagged store simply does not appear under a tag filter. Tags set
by an admin (`tags_source == "admin"`) are never overwritten.
"""
from __future__ import annotations

import re

from ..models import Review, Store

# value -> label shown in the app, in display order.
TAG_LABELS = {
    "menswear": "Menswear",
    "womenswear": "Womenswear",
    "kids": "Kids",
    "ethnic": "Ethnic wear",
    "formal": "Formal wear",
    "denim": "Denim",
    "sportswear": "Sportswear",
    "streetwear": "Streetwear",
    "bridal": "Bridal",
    "vintage": "Vintage & pre-loved",
}

STORE_TYPE_LABELS = {
    "thrift": "Thrift & second-hand",
    "retail_fashion": "Boutiques & local stores",
    "branded": "Brand stores",
    "factory_outlet": "Factory outlets",
}

_RULES = {tag: re.compile(rx, re.I) for tag, rx in {
    "menswear": r"\bmen'?s\b|\bmens\b|\bmenswear\b|\bgents?\b|\bfor men\b",
    "womenswear": r"\bwomen'?s\b|\bwomens\b|\bwomenswear\b|\bladies\b|\bfor women\b",
    "kids": r"\bkids?\b|\bchildren'?s?\b|\bbaby\b|\binfants?\b|\byouth\b",
    "ethnic": (r"\bethnic\b|\bsarees?\b|\bsaris?\b|\bkurtas?\b|\bkurtis?\b|\blehengas?\b|\bsilks?\b"
               r"|\bsalwar\b|\btraditional wear\b|\bhandloom\b|\bkhadi\b"),
    "formal": r"\bformals?\b|\bsuits\b|\bblazers?\b|\bsuiting\b",
    "denim": r"\bdenim\b|\bjeans\b",
    "sportswear": r"\bsportswear\b|\bsports wear\b|\bactivewear\b|\bathletic wear\b|\bgym\s?wear\b",
    "streetwear": r"\bstreetwear\b|\bstreet wear\b|\boversized tees?\b|\bgraphic tees?\b",
    "bridal": r"\bbridal\b|\bbridalwear\b|\bwedding (wear|collection|dress|lehenga)\b",
    "vintage": r"\bvintage\b|\bpre-?loved\b|\bsecond[- ]hand\b|\bthrift",
}.items()}

# Well-known chains. Matched on the store NAME only, as a whole word/phrase.
_BRANDS = {
    "snitch": ["menswear"],
    "rare rabbit": ["menswear"],
    "banana club": ["menswear"],
    "mufti": ["menswear", "denim"],
    "peter england": ["menswear", "formal"],
    "louis philippe": ["menswear", "formal"],
    "arrow": ["menswear", "formal"],
    "raymond": ["menswear", "formal"],
    "p n rao": ["menswear", "formal"],
    "van heusen": ["menswear", "womenswear", "formal"],
    "allen solly": ["menswear", "womenswear", "formal"],
    "manyavar": ["menswear", "ethnic"],
    "biba": ["womenswear", "ethnic"],
    "soch": ["womenswear", "ethnic"],
    "global desi": ["womenswear", "ethnic"],
    "go colors": ["womenswear"],
    "rareism": ["womenswear"],
    "fabindia": ["menswear", "womenswear", "ethnic"],
    "pantaloons": ["menswear", "womenswear", "kids", "ethnic"],
    "westside": ["menswear", "womenswear", "kids"],
    "style union": ["menswear", "womenswear", "kids"],
    "unlimited fashion": ["menswear", "womenswear", "kids"],
    "shoppers stop": ["menswear", "womenswear", "kids"],
    "zudio": ["menswear", "womenswear", "kids"],
    "lifestyle": ["menswear", "womenswear", "kids"],
    "max fashion": ["menswear", "womenswear", "kids"],
    "zara": ["menswear", "womenswear", "kids"],
    "h&m": ["menswear", "womenswear", "kids"],
    "bewakoof": ["menswear", "womenswear", "streetwear"],
    "levi's": ["menswear", "womenswear", "denim"],
    "levis": ["menswear", "womenswear", "denim"],
    "pepe jeans": ["menswear", "womenswear", "denim"],
    "wrangler": ["menswear", "womenswear", "denim"],
    "spykar": ["menswear", "denim"],
    "nike": ["sportswear"],
    "adidas": ["sportswear"],
    "puma": ["sportswear"],
    "reebok": ["sportswear"],
    "decathlon": ["sportswear"],
    "under armour": ["sportswear"],
    "skechers": ["sportswear"],
    "asics": ["sportswear"],
}
_BRAND_RES = [(re.compile(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", re.I), tags)
              for name, tags in _BRANDS.items()]
_BRAND_NAMES = [(re.compile(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", re.I), name)
                for name in _BRANDS]

REVIEW_MENTIONS_NEEDED = 2


def is_known_chain(name: str) -> bool:
    """True when the store name carries one of the well-known brand names above."""
    return any(rx.search(name or "") for rx, _ in _BRAND_RES)


def known_brand(name: str) -> str | None:
    """The well-known brand in a store name ("levi's", "fabindia"), if any."""
    for rx, brand in _BRAND_NAMES:
        if rx.search(name or ""):
            return brand
    return None


def derive_tags(name: str, categories: str = "", description: str = "",
                review_texts: list[str] | None = None) -> list[str]:
    """Tags for one store, in TAG_LABELS order."""
    own = " ".join(p for p in (name, (categories or "").replace(",", " "), description) if p)
    reviews = " ".join(review_texts or [])
    found = set()
    for tag, rx in _RULES.items():
        if rx.search(own) or len(rx.findall(reviews)) >= REVIEW_MENTIONS_NEEDED:
            found.add(tag)
    for rx, tags in _BRAND_RES:
        if rx.search(name or ""):
            found.update(tags)
    return [t for t in TAG_LABELS if t in found]


def split_tags(value: str | None) -> list[str]:
    return [t for t in (value or "").split(",") if t]


def assign_tags(db) -> int:
    """Recompute tags for every store not edited by an admin. Flushes, no commit.
    Returns how many stores changed."""
    texts: dict[str, list[str]] = {}
    for store_id, text in db.query(Review.store_id, Review.text):
        if text:
            texts.setdefault(store_id, []).append(text)
    changed = 0
    for store in db.query(Store).filter(Store.tags_source.is_(None) | (Store.tags_source != "admin")):
        tags = ",".join(derive_tags(store.name, store.categories or "", store.description or "",
                                    texts.get(store.id)))
        if tags != (store.tags or ""):
            store.tags = tags or None
            store.tags_source = "auto" if tags else None
            changed += 1
    db.flush()
    return changed

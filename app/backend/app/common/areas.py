"""Bengaluru area names: the canonical list and how raw locality text maps to it."""
import re

# Canonical Bengaluru localities. Raw `locality_raw` values in the source
# data are messy ("J.P Nagar 5th Phase", "3rd Phase,JP Nagar", "Electronic
# City,Bengaluru", "Koramangala 8th Block"…), which fragmented the same
# neighbourhood into many "areas" and broke exact-match filtering. Any raw
# string containing one of these (ignoring case/punctuation/spacing) is
# collapsed to the canonical name.
KNOWN_AREAS = [
    "Koramangala", "Indiranagar", "JP Nagar", "HSR Layout", "BTM Layout",
    "Jayanagar", "Whitefield", "Electronic City", "Commercial Street",
    "Church Street", "Shivaji Nagar", "Rajajinagar", "Kothanur",
    "Kalasipalaya", "KR Market", "Lingarajapuram", "Mathikere",
    "Bannerghatta Road", "Chandra Layout", "Sriramapura",
    "Sivanchetti Gardens", "Richards Town", "Jayamahal", "Bendre Nagar",
    # More specific must come before shorter substrings they contain:
    # "Btm 1st Stage" before "1st Stage" (both match "btm 1st stage" input,
    # but "btm1ststage" ⊄ "1ststage" so ordering only matters the other way).
    "S G Palya", "Btm 1st Stage", "1st Stage",
    "Old Madiwala", "Malleshwaram", "Hbr Layout",
]

_STREET_SUFFIX_RE = re.compile(r"\s+(main\s+road|road|rd|street|st)\.?$", re.I)


def _squash(s: str) -> str:
    """Lowercase and drop everything but letters/digits, for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def canonical_area(raw: str) -> str:
    """Map a raw locality string to a clean, canonical area name."""
    raw = (raw or "").strip()
    if not raw:
        return "Bengaluru"
    squashed = _squash(raw)
    for area in KNOWN_AREAS:
        if _squash(area) in squashed:
            return area
    # Fallback: strip a trailing ", Bengaluru", take the last comma segment
    # (usually the locality). If that segment is a bare generic suffix word
    # (e.g. "Bapuji,Nagar" -> "Nagar"), merge it with the preceding segment.
    cleaned = re.sub(r",?\s*bengaluru$", "", raw, flags=re.I).strip()
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    if not parts:
        return "Bengaluru"
    seg = parts[-1]
    generic = {"nagar", "layout", "road", "cross", "circle", "block", "phase", "stage"}
    if _squash(seg) in generic and len(parts) >= 2:
        seg = f"{parts[-2]} {seg}"
    seg = _STREET_SUFFIX_RE.sub("", seg).strip()
    return seg or cleaned or "Bengaluru"

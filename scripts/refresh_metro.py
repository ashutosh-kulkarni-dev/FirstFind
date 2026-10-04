"""
Refresh metro_stations_blr.json from OpenStreetMap Overpass API.

Queries Namma Metro route relations within the Bengaluru bounding box,
cleans them into the existing schema, and writes data/metro_stations_blr.json.

Run manually:   python scripts/refresh_metro.py
Run in CI:      see .github/workflows/metro-refresh.yml (weekly schedule)

Output schema (drop-in compatible with existing renderer in Zones.jsx):
{
  "_note": "...",
  "_reviewed": "YYYY-MM",
  "lines": [
    {
      "id": "purple",
      "name": "Purple Line",
      "color": "#7B2D8B",
      "stations": [
        { "name": "...", "lat": 12.xxx, "lng": 77.xxx, "order": 1, "phase": "operational" }
      ]
    }
  ]
}
"""

import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Install requests:  pip install requests")

# Some machines (corporate/AV SSL interception) present a root CA that certifi
# rejects, breaking HTTPS to Overpass with CERTIFICATE_VERIFY_FAILED. truststore
# routes verification through the OS trust store, which does trust that CA.
# Optional: absent on a clean CI runner, where certifi already works — skip quietly.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# Windows consoles default to cp1252 and choke on the status glyphs below; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ── Config ────────────────────────────────────────────────────────────────────

# Primary + mirrors. The main instance frequently returns 504/429 under load;
# on failure we fall through to the next endpoint before giving up.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Bengaluru bounding box (south, west, north, east)
BBOX = "12.7343,77.3791,13.1390,77.8180"

# Known Namma Metro line metadata, keyed by the route relation's `ref` tag
# (Purple / Green / Yellow / …), which is far more stable than its free-text name.
LINE_CONFIG = [
    {"match": ["purple"], "id": "purple", "name": "Purple Line", "color": "#7B2D8B"},
    {"match": ["green"],  "id": "green",  "name": "Green Line",  "color": "#007A3D"},
    {"match": ["yellow"], "id": "yellow", "name": "Yellow Line", "color": "#FFC400"},
    {"match": ["pink"],   "id": "pink",   "name": "Pink Line",   "color": "#E91E8C"},
    {"match": ["blue"],   "id": "blue",   "name": "Blue Line",   "color": "#0072BC"},
]

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "metro_stations_blr.json"

# ── Overpass query ─────────────────────────────────────────────────────────────

# Namma Metro route relations list their stops as bare (unnamed) `stop` nodes in
# travel order. The station NAMES live on separate railway=station entities. So we
# fetch both: the route relations (for ordered stop geometry) and the named station
# nodes/ways (to label each stop by proximity). `>;` pulls member node coords.
QUERY = f"""
[out:json][timeout:90];
(
  relation["route"="subway"]["network"~"Namma Metro|BMRCL",i]({BBOX});
  relation["route"="subway"]["operator"~"BMRCL|Bangalore Metro",i]({BBOX});
);
out body;
>;
out skel qt;

// Named subway station entities, any common tagging variant.
(
  node["railway"="station"]["station"="subway"]({BBOX});
  node["railway"="station"]["network"~"Namma Metro|BMRCL",i]({BBOX});
  node["public_transport"="station"]["subway"="yes"]({BBOX});
  way["railway"="station"]["station"="subway"]({BBOX});
);
out center tags;
"""


# Overpass rejects the default python-requests UA with HTTP 406; identify ourselves.
HEADERS = {
    "User-Agent": "FirstFind-metro-refresh/1.0 (+https://github.com/; contact ashutosh.bhas@gmail.com)",
    "Accept": "application/json",
}


def fetch_overpass(query: str, retries: int = 2) -> dict:
    """Try each Overpass endpoint (retries each) until one returns valid JSON."""
    last_err = None
    for url in OVERPASS_URLS:
        host = url.split("/")[2]
        for attempt in range(retries):
            try:
                resp = requests.post(
                    url, data={"data": query}, headers=HEADERS, timeout=120
                )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                last_err = e
                more = attempt < retries - 1
                print(f"  {host} attempt {attempt+1} failed: {e}." + (" Retrying in 10s…" if more else " Next endpoint…"))
                if more:
                    time.sleep(10)
    raise last_err


# ── Parsing ────────────────────────────────────────────────────────────────────

def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in km. Local copy so the script stays dependency-free."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def match_line_config(relation_tags: dict):
    """Match a route relation to a line config by its `ref` tag (then name)."""
    hay = f"{relation_tags.get('ref','')} {relation_tags.get('name','')}".lower()
    for cfg in LINE_CONFIG:
        if any(kw in hay for kw in cfg["match"]):
            return cfg
    return None


def node_coords(elements: list) -> dict:
    """Build node_id → (lat, lng) lookup. Overpass names longitude 'lon'."""
    return {
        el["id"]: (el["lat"], el["lon"])
        for el in elements
        if el["type"] == "node" and "lat" in el
    }


def named_stations(elements: list) -> list:
    """
    Collect named subway station entities as [(name, lat, lng)].
    Ways report their position under `center` (from `out center`).
    """
    out = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        if el["type"] == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:  # way / relation with a computed center
            c = el.get("center", {})
            lat, lng = c.get("lat"), c.get("lon")
        if lat is not None and lng is not None:
            out.append((name, lat, lng))
    return out


def nearest_name(lat: float, lng: float, stations: list, max_m: float = 200.0):
    """Nearest named station to a stop coord, or None beyond max_m."""
    best, best_km = None, float("inf")
    for name, slat, slng in stations:
        d = _haversine_km(lat, lng, slat, slng)
        if d < best_km:
            best, best_km = name, d
    return best if best is not None and best_km * 1000 <= max_m else None


def extract_stops(relation: dict, nodes: dict) -> list:
    """
    Extract stops from a route relation IN MEMBER ORDER.

    A route=subway relation lists members in physical travel sequence, so we
    preserve that order and never re-sort by coordinate (a line is a curve, not
    monotonic in lat/lng). Namma Metro stops are bare `stop` nodes with no name;
    names are attached later by matching to named station entities.

    Returns list of {lat, lng} in line order.
    """
    stops = []
    for member in relation.get("members", []):
        if member["type"] != "node" or not member.get("role", "").startswith("stop"):
            continue
        node_id = member["ref"]
        if node_id not in nodes:
            continue
        lat, lng = nodes[node_id]
        stops.append({"lat": round(lat, 6), "lng": round(lng, 6)})
    return stops


def clean_name(name: str) -> str:
    """Strip only metro-specific suffixes; preserve real words like 'Station'.

    Correct: 'Indiranagar Metro Station' -> 'Indiranagar',
             'City Railway Station' -> 'City Railway Station' (untouched).
    """
    n = re.sub(r"\s+metro\s+station\s*$", "", name, flags=re.IGNORECASE)  # "… Metro Station"
    n = re.sub(r"\s*\(?\s*metro\s*\)?\s*$", "", n, flags=re.IGNORECASE)    # trailing "Metro"/"(Metro)"
    return n.strip() or "Unknown"


def dedupe_consecutive(stations: list) -> list:
    """
    Collapse consecutive stops that resolve to the same station name
    (entry/exit nodes of one physical station), preserving member order.
    Non-consecutive repeats are left alone — a name legitimately recurring
    later would signal a folded round-trip relation, which build_json already
    guards against by picking a single forward direction (the longest candidate).
    """
    kept = []
    for s in stations:
        if kept and kept[-1]["name"] == s["name"]:
            continue
        kept.append(s)
    return kept


# ── Validation ───────────────────────────────────────────────────────────────

def validate(result: dict, min_stations: int = 5, max_jump_km: float = 4.0) -> list:
    """
    Sanity-check the built data before it is allowed to overwrite the asset.
    Returns a list of human-readable problems (empty list == OK).

    The consecutive-jump check is the guard against ordering bugs: adjacent
    stations on a real line are always close, so a large gap means the sequence
    is scrambled (this is exactly what the old lat/lng sort produced).
    """
    problems = []
    for line in result["lines"]:
        sts = line["stations"]
        if len(sts) < min_stations:
            problems.append(f"{line['id']}: only {len(sts)} stations (< {min_stations})")
        for a, b in zip(sts, sts[1:]):
            jump = _haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
            if jump > max_jump_km:
                problems.append(
                    f"{line['id']}: {a['name']} -> {b['name']} jumps {jump:.1f} km "
                    f"(> {max_jump_km}) - ordering looks wrong"
                )
    return problems


# ── Main ───────────────────────────────────────────────────────────────────────

def build_json(data: dict) -> dict:
    elements = data.get("elements", [])
    nodes = node_coords(elements)
    stations_idx = named_stations(elements)  # (name, lat, lng) for label matching

    relations = [el for el in elements if el["type"] == "relation"]
    print(f"  Found {len(relations)} relation(s), {len(nodes)} node(s), "
          f"{len(stations_idx)} named station(s)")

    lines_by_id: dict = {}

    for rel in relations:
        tags = rel.get("tags", {})
        cfg = match_line_config(tags)
        if not cfg:
            print(f"  Skipping unmatched relation: {tags.get('name', rel['id'])}")
            continue

        stops = extract_stops(rel, nodes)
        # Label each ordered stop by its nearest named station entity.
        for i, s in enumerate(stops):
            nm = nearest_name(s["lat"], s["lng"], stations_idx)
            s["name"] = clean_name(nm) if nm else f"Stop {i + 1}"

        line_id = cfg["id"]
        if line_id not in lines_by_id:
            lines_by_id[line_id] = {
                "id": cfg["id"],
                "name": cfg["name"],
                "color": cfg["color"],
                "_candidates": [],  # one ordered stop list per relation
            }
        # Keep each relation's stops as a SEPARATE ordered candidate — do not
        # flatten across relations, or a forward + reverse pair would fold together.
        lines_by_id[line_id]["_candidates"].append(stops)

    # Pick the canonical direction per line, preserve order, assign order + phase
    lines = []
    for line_id, line in lines_by_id.items():
        candidates = line.pop("_candidates")
        # The full-line direction is the relation with the most stops. Picking one
        # (instead of merging) avoids duplicating stations from the reverse route.
        best = max(candidates, key=len) if candidates else []
        unique = dedupe_consecutive(best)  # preserves member order

        stations = []
        for i, s in enumerate(unique):
            stations.append({
                "name": s["name"],
                "lat": s["lat"],
                "lng": s["lng"],
                "order": i + 1,          # order == OSM member sequence, never re-sorted
                "phase": "operational",  # all OSM-confirmed stop nodes are operational
            })

        if not stations:
            print(f"  Warning: line '{line_id}' has 0 stations, skipping")
            continue

        line["stations"] = stations
        lines.append(line)
        print(f"  {line['name']}: {len(stations)} stations")

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return {
        "_note": f"Namma Metro — auto-refreshed from OpenStreetMap Overpass API",
        "_reviewed": month,
        "_source": "OpenStreetMap contributors (ODbL)",
        "lines": lines,
    }


def main():
    print("Querying Overpass API for Namma Metro…")
    data = fetch_overpass(QUERY)
    print("Parsing…")
    result = build_json(data)

    if not result["lines"]:
        sys.exit("ERROR: No metro lines extracted. Check the Overpass query / BBOX.")

    problems = validate(result)
    if problems:
        print("Validation FAILED — refusing to overwrite the asset:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit("ERROR: Built data failed sanity checks (see above). Asset left unchanged.")
    print("Validation passed.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {OUTPUT_PATH} ({sum(len(l['stations']) for l in result['lines'])} total stations)")


if __name__ == "__main__":
    main()

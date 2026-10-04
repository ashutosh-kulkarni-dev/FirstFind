"""Geospatial clustering of stores into thrift zones.

Geography-only clustering: HDBSCAN over (lat, lng), with a geography-only
KMeans fallback. Zones are named after their dominant area (most stores) with
locality_raw as tiebreaker — no archetype labels (Budget/Premium/Hidden Gem).

Radius is the 90th-percentile haversine distance from centroid to members (D16),
which shrugs off a single outlier store while bounding the real extent.

Return contract:
    [{label, center_lat, center_lng, radius_km, store_ids, avg_score, avg_price}]
"""
import math
import numpy as np
from collections import Counter
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.preprocessing import StandardScaler

from ..config import N_ZONES, SEED, MAX_RADIUS_KM


def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _real_radius(center_lat, center_lng, members: list[dict]) -> float:
    """90th-percentile haversine from centroid to each member, capped at MAX_RADIUS_KM."""
    if not members:
        return 0.0
    dists = [_haversine_km(center_lat, center_lng, m["lat"], m["lng"]) for m in members]
    radius = float(np.percentile(dists, 90))
    return round(min(radius, MAX_RADIUS_KM), 3)


def _geographic_label(members: list[dict]) -> str:
    """Dominant area name; tiebreak by locality_raw frequency."""
    area_counts = Counter(m["area"] for m in members if m.get("area"))
    if not area_counts:
        return "Bengaluru"
    top_count = area_counts.most_common(1)[0][1]
    top_areas = [a for a, c in area_counts.items() if c == top_count]
    if len(top_areas) == 1:
        return top_areas[0]
    # Tiebreak: pick the area whose members have the most common locality_raw
    loc_counts = Counter(
        m["locality_raw"] for m in members
        if m.get("area") in top_areas and m.get("locality_raw")
    )
    if loc_counts:
        best_loc = loc_counts.most_common(1)[0][0]
        # Return the area containing this locality
        for m in members:
            if m.get("locality_raw") == best_loc and m.get("area") in top_areas:
                return m["area"]
    return top_areas[0]


def _hdbscan_labels(Xgeo: np.ndarray) -> np.ndarray | None:
    """Return cluster labels (noise reattached), or None if fewer than 2 clusters found."""
    n = len(Xgeo)
    for mcs in range(4, max(6, n // 3)):
        labels = HDBSCAN(min_cluster_size=mcs, copy=True).fit_predict(Xgeo)
        clusters = sorted(c for c in set(labels) if c != -1)
        if 2 <= len(clusters) <= N_ZONES:
            return _reattach_noise(Xgeo, labels, clusters)
    return None


def _reattach_noise(Xgeo, labels, clusters) -> np.ndarray:
    centroids = {c: Xgeo[labels == c].mean(axis=0) for c in clusters}
    out = labels.copy()
    for i in np.where(labels == -1)[0]:
        out[i] = min(clusters, key=lambda c: np.linalg.norm(Xgeo[i] - centroids[c]))
    return out


def _kmeans_labels(usable: list[dict]) -> np.ndarray:
    """Fallback: KMeans on geography only (lat/lng, no price/score)."""
    lat = np.array([r["lat"] for r in usable])
    lng = np.array([r["lng"] for r in usable])
    X = np.column_stack([lat, lng])
    return KMeans(n_clusters=N_ZONES, random_state=SEED, n_init=10).fit_predict(X)


def cluster_stores(rows: list[dict]) -> list[dict]:
    """rows: [{id, lat, lng, area, locality_raw, price, score, review_count}].

    Returns zones with geographic names and real radius. Price/score are
    included as displayed facts only — they do not influence cluster membership.
    """
    usable = [r for r in rows if r["lat"] is not None and r["lng"] is not None]
    if len(usable) < N_ZONES:
        return []

    lat = np.array([r["lat"] for r in usable])
    lng = np.array([r["lng"] for r in usable])

    Xgeo = StandardScaler().fit_transform(np.column_stack([lat, lng]))
    labels = _hdbscan_labels(Xgeo)
    if labels is None:
        labels = _kmeans_labels(usable)

    zones = []
    for k in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == k]
        if not idx:
            continue
        members = [usable[i] for i in idx]
        center_lat = float(lat[idx].mean())
        center_lng = float(lng[idx].mean())
        prices = [m["price"] for m in members if m.get("price") is not None]
        scores = [m["score"] for m in members if m.get("score") is not None]
        zones.append({
            "label": _geographic_label(members),
            "center_lat": center_lat,
            "center_lng": center_lng,
            "radius_km": _real_radius(center_lat, center_lng, members),
            "store_ids": [m["id"] for m in members],
            "avg_score": round(float(np.mean(scores)), 2) if scores else None,
            "avg_price": round(float(np.mean(prices)), 0) if prices else None,
        })
    return zones

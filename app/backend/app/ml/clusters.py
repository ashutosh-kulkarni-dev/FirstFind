"""Cluster discovery helpers — Phase 2+ (Mode B).

discover_clusters  — reads precomputed Zone rows (Mode A, Phase 1).
find_cluster       — coordinate + radius query returning a live result (Mode B, Phase 2).
split_cluster      — recursive HDBSCAN + KMeans fallback split (Phase 4).
"""
import math
from collections import Counter

import numpy as np
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from ..config import DEFAULT_MAX_SHOPS, DEFAULT_MIN_SHOPS, SEED
from ..models import Store, Zone
from ..utils import STORE_HAS_COORDS, haversine_km, store_to_dict, zone_to_dict


def discover_clusters(db: Session) -> list[dict]:
    """Return all precomputed geographic zones as dicts (Mode A)."""
    return [zone_to_dict(z) for z in db.query(Zone).all()]


def _geo_label(stores: list) -> str:
    counts = Counter(s.area for s in stores if s.area)
    return counts.most_common(1)[0][0] if counts else "This area"


def _real_radius(center_lat, center_lng, stores: list) -> float:
    if not stores:
        return 0.0
    dists = [haversine_km(center_lat, center_lng, s.lat, s.lng) for s in stores]
    return round(float(np.percentile(dists, 90)) if len(dists) >= 2 else dists[0], 3)


def _store_stats(stores: list) -> tuple:
    scores = [s.experience_score for s in stores if s.experience_score is not None]
    prices = [
        (s.price_min + s.price_max) / 2
        for s in stores if s.price_min is not None and s.price_max is not None
    ]
    avg_score = round(float(np.mean(scores)), 2) if scores else None
    avg_price = round(float(np.mean(prices)), 0) if prices else None
    return avg_score, avg_price


def find_cluster(
    db: Session,
    lat: float,
    lng: float,
    radius_km: float,
    min_shops: int = DEFAULT_MIN_SHOPS,
    max_shops: int = DEFAULT_MAX_SHOPS,
) -> dict:
    """Mode B: find stores within radius, compute real radius + geographic name.

    Returns:
      {label, center_lat, center_lng, radius_km, store_count, stores,
       over_cap, avg_score, avg_price, honest_empty}

    over_cap=True when count > max_shops — the frontend offers a split.
    Never truncates: full store list always returned.
    """
    in_radius = []
    for s in db.query(Store).filter(*STORE_HAS_COORDS).all():
        d = haversine_km(lat, lng, s.lat, s.lng)
        if d <= radius_km:
            in_radius.append((d, s))

    in_radius.sort(key=lambda x: x[0])
    stores = [s for _, s in in_radius]

    if not stores:
        return {
            "label": None, "center_lat": lat, "center_lng": lng,
            "radius_km": radius_km, "store_count": 0, "stores": [],
            "over_cap": False, "avg_score": None, "avg_price": None,
            "honest_empty": True,
        }

    dists = [d for d, _ in in_radius]
    real_radius = float(np.percentile(dists, 90)) if len(dists) >= 2 else dists[0]
    avg_score, avg_price = _store_stats(stores)

    return {
        "label": _geo_label(stores),
        "center_lat": lat, "center_lng": lng,
        "radius_km": round(real_radius, 3),
        "store_count": len(stores),
        "stores": [store_to_dict(s, lat, lng) for s in stores],
        "over_cap": len(stores) > max_shops,
        "avg_score": avg_score, "avg_price": avg_price,
        "honest_empty": False,
    }


def split_cluster(
    stores_in: list,           # list of Store ORM objects already inside the radius
    center_lat: float,
    center_lng: float,
    max_shops: int = DEFAULT_MAX_SHOPS,
) -> list[dict]:
    """Split an over-cap cluster into sub-zones.

    Strategy (§13 of the plan):
      1. Try HDBSCAN at progressively tighter min_cluster_size until every
         sub-cluster has <= max_shops stores.
      2. Fallback: KMeans(k = ceil(count / max_shops)) — always terminates.

    Invariant: union of all sub-zone store_ids == stores_in (no store dropped).
    Each sub-zone has store_count <= max_shops (best effort; KMeans may produce
    slightly over on edge cases when count isn't divisible).

    Returns list of sub-zone dicts compatible with find_cluster output shape.
    """
    usable = [s for s in stores_in if s.lat is not None and s.lng is not None]
    if not usable:
        return []

    n = len(usable)
    k_target = math.ceil(n / max_shops)

    lats = np.array([s.lat for s in usable])
    lngs = np.array([s.lng for s in usable])
    Xgeo = StandardScaler().fit_transform(np.column_stack([lats, lngs]))

    labels = _try_hdbscan_split(Xgeo, k_target, max_shops)
    if labels is None:
        labels = _kmeans_split(Xgeo, k_target)

    return _build_sub_zones(usable, labels, lats, lngs, center_lat, center_lng)


def _try_hdbscan_split(Xgeo: np.ndarray, k_target: int, max_shops: int):
    """Try HDBSCAN with tightening min_cluster_size until all clusters <= max_shops.
    Returns labels array or None if no valid split found."""
    n = len(Xgeo)
    for mcs in range(2, max(3, n // k_target) + 1):
        raw = HDBSCAN(min_cluster_size=mcs, copy=True).fit_predict(Xgeo)
        clusters = sorted(c for c in set(raw) if c != -1)
        if len(clusters) < 2:
            continue
        # Reattach noise to nearest cluster
        labels = _reattach_noise(Xgeo, raw, clusters)
        sizes = [int((labels == c).sum()) for c in clusters]
        if all(s <= max_shops for s in sizes):
            return labels
    return None


def _reattach_noise(Xgeo, labels, clusters) -> np.ndarray:
    centroids = {c: Xgeo[labels == c].mean(axis=0) for c in clusters}
    out = labels.copy()
    for i in np.where(labels == -1)[0]:
        out[i] = min(clusters, key=lambda c: np.linalg.norm(Xgeo[i] - centroids[c]))
    return out


def _kmeans_split(Xgeo: np.ndarray, k: int) -> np.ndarray:
    return KMeans(n_clusters=max(2, k), random_state=SEED, n_init=10).fit_predict(Xgeo)


def _build_sub_zones(usable, labels, lats, lngs, parent_lat, parent_lng) -> list[dict]:
    sub_zones = []
    for k in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == k]
        if not idx:
            continue
        members = [usable[i] for i in idx]
        clat = float(lats[idx].mean())
        clng = float(lngs[idx].mean())
        avg_score, avg_price = _store_stats(members)
        sub_zones.append({
            "label": _geo_label(members),
            "center_lat": clat,
            "center_lng": clng,
            "radius_km": _real_radius(clat, clng, members),
            "store_count": len(members),
            "stores": [store_to_dict(s, parent_lat, parent_lng) for s in members],
            "over_cap": False,
            "avg_score": avg_score,
            "avg_price": avg_price,
            "honest_empty": False,
        })
    return sub_zones

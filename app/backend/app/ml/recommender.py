"""Hybrid recommender: content similarity, blended with collaborative filtering
where there is enough interaction data to trust it.

Content similarity between two stores combines
  * what they are: store kind, tags, categories and (real, not estimated)
    price tier — cosine similarity of those features; and
  * where they are: exp(-distance / 2 km), so a store 1 km away scores 0.61
    and one 5 km away 0.08.

    content = 0.7 * attributes + 0.3 * distance

Collaborative filtering (item-item cosine over user interactions: view 1,
save 3, a 4-5 star review 4) is blended in only for pairs of stores that each
have interactions from at least MIN_USERS_FOR_CF users. Before, CF was always
blended at 60%, and with no interactions in the data every similarity was
capped at 40% — which is why every match showed "40%".

Every pick carries a reason ("Because you saved X", "Similar style, 1.2 km
away"), and a list never holds more than one branch of the same chain.
Fitting: Recommender.build (startup, refit task, daily job). Serving reads:
similar_rows, user_rec_rows and user_recs, from the precomputed tables.
"""
from __future__ import annotations

import math
import re

import numpy as np

from ..data.tags import known_brand

WEIGHTS = {"view": 1.0, "save": 3.0, "like": 4.0}
# What the reason says about the user's strongest signal for a store.
_SIGNAL_REASON = {"like": "Because you rated {name} highly",
                  "save": "Because you saved {name}",
                  "view": "Because you looked at {name}"}
ALPHA = 0.5               # CF share of the blend, where CF is trusted
MIN_USERS_FOR_CF = 3      # a store needs this many users before CF counts for it
W_ATTRIBUTES, W_DISTANCE = 0.7, 0.3
DISTANCE_SCALE_KM = 2.0
# How a reason names a store kind: "Also a thrift store".
_KIND_NOUN = {"thrift": "thrift store", "retail_fashion": "local boutique",
              "branded": "brand store", "factory_outlet": "factory outlet"}
MATCH_SHOWN_FROM = 0.5    # below this a "% match" means little and is not shown

# Feature weights inside the attribute vector (before cosine).
_W_KIND, _W_TAG, _W_CATEGORY, _W_PRICE = 1.0, 1.0, 0.5, 0.8
_PRICE_TIERS = 3          # budget / mid / premium

_SEPARATOR_RE = re.compile(r"\s+[-–|]\s+|[,|(]")
_NON_WORD_RE = re.compile(r"[^a-z0-9 ]+")


def _norm(text: str) -> str:
    return " ".join(_NON_WORD_RE.sub(" ", (text or "").lower().replace("'", "")).split())


def chain_key(name: str) -> str:
    """The brand part of a store name: "Fabindia, HSR Layout", "FABINDIA - JP
    Nagar" and "Fabindia Experience Center" all give "fabindia"."""
    brand = known_brand(name)
    if brand:
        return _norm(brand)
    return _norm(_SEPARATOR_RE.split(name or "", maxsplit=1)[0])


# First words too common to mean "same brand" ("Thrift Hands", "The Preloved Co").
_COMMON_FIRST_WORDS = {"the", "thrift", "vintage", "sri", "shri", "shree", "new", "fashion",
                       "fashions", "style", "studio", "boutique", "store", "shop", "my", "kids"}


def chain_keys(names: list[str]) -> list[str | None]:
    """chain_key for each name, merged across the list: "pantaloons south zonal
    office" joins "pantaloons" when another store is just "Pantaloons ...".
    None for a store with no other branch in the list."""
    keys = [chain_key(n) for n in names]
    single = set(keys)
    merged = []
    for k in keys:
        first = k.split(" ", 1)[0]
        if " " in k and first in single and len(first) >= 4 and first not in _COMMON_FIRST_WORDS:
            k = first
        merged.append(k)
    counts: dict[str, int] = {}
    for k in merged:
        counts[k] = counts.get(k, 0) + 1
    return [k if k and counts[k] > 1 else None for k in merged]


def price_tier(store) -> int | None:
    """0 budget / 1 mid / 2 premium from the store's own prices; None when the
    prices are missing or only a generic estimate for its kind."""
    if getattr(store, "price_estimated", False):
        return None
    lo, hi = store.price_min, store.price_max
    if lo is None and hi is None:
        return None
    mid = ((lo or hi) + (hi or lo)) / 2
    return 0 if mid < 700 else 1 if mid < 2000 else 2


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _cosine_sim(M: np.ndarray) -> np.ndarray:
    """Column-wise cosine similarity of a (rows x items) matrix -> (items x items)."""
    norms = np.linalg.norm(M, axis=0, keepdims=True)
    Mn = np.divide(M, norms, out=np.zeros_like(M), where=norms > 0)
    sim = Mn.T @ Mn
    np.fill_diagonal(sim, 0.0)
    return sim


def _distance_text(km: float) -> str:
    if km < 1:
        return f"{max(50, int(round(km * 1000, -1)))} m away"
    return f"{km:.1f} km away"


class Recommender:
    def __init__(self):
        self.store_ids: list[str] = []
        self._idx: dict[str, int] = {}
        self.names: list[str] = []
        self.chains: list[str | None] = []
        self.kinds: list[str] = []
        self.styles: list[set[str]] = []            # tags + categories, for reasons
        self.sim: np.ndarray | None = None          # hybrid item-item similarity
        self.attr_sim: np.ndarray | None = None
        self.dist_km: np.ndarray | None = None
        self.cf_used: np.ndarray | None = None      # bool: CF blended for this pair
        self.user_vectors: dict[int, np.ndarray] = {}
        self.user_signals: dict[int, dict[int, str]] = {}  # uid -> {item: strongest kind}

    # ------------------------------------------------------------------ fit

    def build(self, db):
        """(Re)fit from current DB state and persist the results to the DB.

        Called at startup and by the background refit task / batch pipeline —
        never on the request path. The caller commits.
        """
        from ..models import Interaction, Store
        # Only visible (geocoded, active) stores may appear in any list.
        stores = db.query(Store).filter(Store.lat.isnot(None),
                                        Store.lng.isnot(None),
                                        Store.is_active.isnot(False)).all()
        interactions = [(i.user_id, i.store_id, i.kind)
                        for i in db.query(Interaction).all()]
        if stores:
            self.fit(interactions, [s.id for s in stores], stores)
            self._persist(db)

    def fit(self, interactions, store_ids, stores):
        """interactions: [(user_id, store_id, kind)]; stores: [Store]."""
        by_id = {s.id: s for s in stores}
        self.store_ids = list(store_ids)
        self._idx = {sid: i for i, sid in enumerate(self.store_ids)}
        ordered = [by_id[sid] for sid in self.store_ids]
        n = len(ordered)
        self.names = [s.name or s.id for s in ordered]
        self.kinds = [s.store_type or "thrift" for s in ordered]
        self.styles = [set(_split(s.tags)) | {c.lower() for c in _split(s.categories)}
                       for s in ordered]

        self.chains = chain_keys([s.name for s in ordered])

        # ---- content: attributes + distance ----
        self.attr_sim = _cosine_sim(self._attribute_matrix(ordered).T)
        lat = np.radians([s.lat for s in ordered])
        lng = np.radians([s.lng for s in ordered])
        dlat = lat[:, None] - lat[None, :]
        dlng = lng[:, None] - lng[None, :]
        a = np.sin(dlat / 2) ** 2 + np.cos(lat)[:, None] * np.cos(lat)[None, :] * np.sin(dlng / 2) ** 2
        self.dist_km = 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        content = W_ATTRIBUTES * self.attr_sim + W_DISTANCE * np.exp(-self.dist_km / DISTANCE_SCALE_KM)

        # ---- collaborative filtering, where there is enough data ----
        users = sorted({u for u, _, _ in interactions})
        uidx = {u: i for i, u in enumerate(users)}
        M = np.zeros((max(len(users), 1), n))
        signals: dict[int, dict[int, str]] = {}
        for u, sid, kind in interactions:
            j = self._idx.get(sid)
            if j is None:
                continue
            M[uidx[u], j] += WEIGHTS.get(kind, 1.0)
            best = signals.setdefault(u, {})
            if WEIGHTS.get(kind, 1.0) > WEIGHTS.get(best.get(j, ""), 0.0):
                best[j] = kind
        cf = _cosine_sim(M) if users else np.zeros((n, n))
        enough = (M > 0).sum(axis=0) >= MIN_USERS_FOR_CF
        self.cf_used = np.outer(enough, enough) & (cf > 0)
        self.sim = np.where(self.cf_used, ALPHA * cf + (1 - ALPHA) * content, content)
        np.fill_diagonal(self.sim, 0.0)
        self.user_vectors = {u: M[uidx[u]] for u in users}
        self.user_signals = signals

    def _attribute_matrix(self, stores) -> np.ndarray:
        """(items x features): kind one-hot, tags and categories multi-hot,
        price tier one-hot. Each block is weighted before the cosine."""
        kinds = sorted({s.store_type or "thrift" for s in stores})
        tags = sorted({t for s in stores for t in _split(s.tags)})
        cats = sorted({c.lower() for s in stores for c in _split(s.categories)})
        k_at = {k: i for i, k in enumerate(kinds)}
        t_at = {t: len(kinds) + i for i, t in enumerate(tags)}
        c_at = {c: len(kinds) + len(tags) + i for i, c in enumerate(cats)}
        p0 = len(kinds) + len(tags) + len(cats)
        X = np.zeros((len(stores), p0 + _PRICE_TIERS))
        for row, s in enumerate(stores):
            X[row, k_at[s.store_type or "thrift"]] = _W_KIND
            for t in _split(s.tags):
                X[row, t_at[t]] = _W_TAG
            for c in _split(s.categories):
                X[row, c_at[c.lower()]] = _W_CATEGORY
            tier = price_tier(s)
            if tier is not None:
                X[row, p0 + tier] = _W_PRICE
        return X

    # ------------------------------------------------------------- ranking

    def _diverse(self, order, scores, n, exclude_chain=None):
        """Walk `order` (best first), keeping at most one store per chain."""
        out, seen = [], set()
        if exclude_chain:
            seen.add(exclude_chain)
        for j in order:
            sc = float(scores[j])
            if not math.isfinite(sc) or sc <= 0:
                break   # ranked desc, so the rest are no better
            chain = self.chains[j]
            if chain and chain in seen:
                continue
            if chain:
                seen.add(chain)
            out.append((int(j), sc))
            if len(out) == n:
                break
        return out

    def similar_ranked(self, i: int, n: int) -> list[tuple[int, float, str]]:
        """[(item, score, reason)] most similar to item i — other branches of
        its own chain are left out."""
        scores = self.sim[i]
        order = np.argsort(scores)[::-1]
        return [(j, sc, self._similar_reason(i, j))
                for j, sc in self._diverse(order, scores, n, exclude_chain=self.chains[i])]

    def user_ranked(self, user_id: int, n: int) -> list[tuple[int, float, str]]:
        vec = self.user_vectors.get(user_id)
        if self.sim is None or vec is None or vec.sum() == 0:
            return []
        contrib = self.sim * vec[None, :]          # [rec j, user's store i]
        scores = contrib.sum(axis=1)
        scores[vec > 0] = -np.inf                  # don't recommend already-seen
        # A rec from the same chain as a store the user already knows adds little.
        known_chains = {self.chains[i] for i in np.flatnonzero(vec) if self.chains[i]}
        order = [j for j in np.argsort(scores)[::-1]
                 if not (self.chains[j] and self.chains[j] in known_chains)]
        # Take a wider pool, then alternate between the stores that led to each
        # pick, so one strong signal (a single 5-star review) cannot fill the list.
        pool = self._diverse(order, scores, n * 3)
        by_source: dict[int, list[tuple[int, float]]] = {}
        for j, sc in pool:
            by_source.setdefault(int(np.argmax(contrib[j])), []).append((j, sc))
        queues = sorted(by_source.items(), key=lambda kv: -kv[1][0][1])
        out = []
        while len(out) < n and any(q for _, q in queues):
            for src, q in queues:
                if q and len(out) < n:
                    j, sc = q.pop(0)
                    kind = self.user_signals.get(user_id, {}).get(src, "view")
                    out.append((j, sc, _SIGNAL_REASON[kind].format(name=self.names[src])))
        return out

    def _similar_reason(self, i: int, j: int) -> str:
        if self.cf_used is not None and self.cf_used[i, j]:
            style = "People who liked this also liked it"
        elif self.styles[i] & self.styles[j]:      # they share a tag or category
            style = "Similar style"
        elif self.kinds[i] == self.kinds[j]:
            style = f"Also a {_KIND_NOUN.get(self.kinds[j], 'similar store')}"
        else:
            style = None
        dist = _distance_text(float(self.dist_km[i, j]))
        return f"{style}, {dist}" if style else dist.capitalize()

    # -------------------------------------------------------------- persist

    def _persist(self, db, n_similar: int = 8, n_recs: int = 12) -> None:
        """Write the ranked lists (exactly what the methods above return) to
        the DB for stateless serving. Rewrites both tables; the caller commits."""
        from ..models import StoreSimilarity, UserRecommendation
        db.query(StoreSimilarity).delete()
        db.query(UserRecommendation).delete()
        if self.sim is None:
            db.flush()
            return
        for i, sid in enumerate(self.store_ids):
            for rank, (j, sc, reason) in enumerate(self.similar_ranked(i, n_similar)):
                db.add(StoreSimilarity(store_id=sid, similar_id=self.store_ids[j], rank=rank,
                                       score=round(sc, 4), reason=reason))
        for uid in self.user_vectors:
            for rank, (j, sc, reason) in enumerate(self.user_ranked(uid, n_recs)):
                db.add(UserRecommendation(user_id=uid, store_id=self.store_ids[j], rank=rank,
                                          score=round(sc, 4), reason=reason))
        db.flush()


# module-level singleton, fit at startup
recommender = Recommender()


def match_pct(score: float | None) -> int | None:
    """A "% match" for display, or None when the similarity is too weak to mean much."""
    if score is None or score < MATCH_SHOWN_FROM:
        return None
    return min(99, round(score * 100))


def similar_rows(db, store_id: str, n: int = 4) -> list[tuple[str, float | None, str | None]]:
    """[(store id, score, reason)] — precomputed, with an in-memory fallback for
    the window between a fresh boot and the first persisted refit."""
    from ..models import StoreSimilarity
    rows = (db.query(StoreSimilarity)
            .filter(StoreSimilarity.store_id == store_id)
            .order_by(StoreSimilarity.rank).limit(n).all())
    if rows:
        return [(r.similar_id, r.score, r.reason) for r in rows]
    r = recommender
    if r.sim is None or store_id not in r._idx:
        return []
    return [(r.store_ids[j], sc, reason) for j, sc, reason in r.similar_ranked(r._idx[store_id], n)]


def user_rec_rows(db, user_id: int, n: int = 6) -> list[tuple[str, str | None]]:
    """[(store id, reason)] — precomputed per-user picks, with in-memory fallback."""
    from ..models import UserRecommendation
    rows = (db.query(UserRecommendation)
            .filter(UserRecommendation.user_id == user_id)
            .order_by(UserRecommendation.rank).limit(n).all())
    if rows:
        return [(r.store_id, r.reason) for r in rows]
    r = recommender
    return [(r.store_ids[j], reason) for j, _, reason in r.user_ranked(user_id, n)]


def user_recs(db, user_id: int, n: int = 6) -> list[str]:
    return [sid for sid, _ in user_rec_rows(db, user_id, n)]


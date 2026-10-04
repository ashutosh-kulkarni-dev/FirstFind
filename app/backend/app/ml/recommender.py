"""Hybrid recommender: collaborative filtering blended with content similarity.

Phase 3 of the upgrade plan. The core is still item-item cosine CF over implicit
feedback (view=1, save=2, like=3), but pure CF cold-starts badly — a brand-new
store with no interactions has no neighbours, and a user with sparse history gets
weak recs. So we blend the CF item-item matrix with a **content** item-item matrix
built from each store's attributes (categories, price band, zone, quality):

    sim = alpha * CF_sim + (1 - alpha) * content_sim

Content links survive with zero interaction data, so cold stores still get
neighbours and sparse users still get sensible picks. When interactions are rich,
CF dominates. Public interface (build / recommend_for_user / similar_stores) is
unchanged.
"""
import numpy as np

WEIGHTS = {"view": 1.0, "save": 2.0, "like": 3.0}
ALPHA = 0.6  # CF weight; (1 - ALPHA) is the content weight


def _cosine_sim(M: np.ndarray) -> np.ndarray:
    """Column-wise cosine similarity of a (rows x items) matrix -> (items x items)."""
    norms = np.linalg.norm(M, axis=0, keepdims=True) + 1e-9
    Mn = M / norms
    sim = Mn.T @ Mn
    np.fill_diagonal(sim, 0.0)
    return sim


class Recommender:
    def __init__(self):
        self.store_ids: list[str] = []
        self._idx: dict[str, int] = {}
        self.sim: np.ndarray | None = None          # hybrid item-item similarity
        self.user_vectors: dict[int, np.ndarray] = {}

    def build(self, db):
        """(Re)fit from current DB state and persist the results to the DB.

        Called at startup and by the background refit task / batch pipeline —
        never on the request path. After fitting the in-memory matrix it writes
        the top-N similar-store and per-user rec lists to the DB so serving is
        stateless (identical across workers, survives restart). The caller is
        responsible for committing the session.
        """
        from ..models import Interaction, Store
        # Only fit on visible (geocoded) stores. Hidden, no-coordinate stores
        # must never appear in a similar-store or recommendation list; excluding
        # them here keeps them out of both the matrix and the persisted tables.
        stores = db.query(Store).filter(Store.lat.isnot(None),
                                        Store.lng.isnot(None)).all()
        interactions = [(i.user_id, i.store_id, i.kind)
                        for i in db.query(Interaction).all()]
        store_ids = [s.id for s in stores]
        if store_ids:
            self.fit(interactions, store_ids, stores)
            self._persist(db)

    def fit(self, interactions, store_ids, stores):
        """interactions: [(user_id, store_id, kind)]; stores: [Store]."""
        self.store_ids = store_ids
        self._idx = {sid: i for i, sid in enumerate(store_ids)}
        n = len(store_ids)

        # ---- collaborative-filtering item-item similarity ----
        users = sorted({u for u, _, _ in interactions})
        uidx = {u: i for i, u in enumerate(users)}
        M = np.zeros((max(len(users), 1), n))
        for u, sid, kind in interactions:
            if sid in self._idx:
                M[uidx[u], self._idx[sid]] += WEIGHTS.get(kind, 1.0)
        cf_sim = _cosine_sim(M) if users else np.zeros((n, n))

        # ---- content item-item similarity ----
        content_sim = _cosine_sim(self._content_matrix(stores).T)

        # ---- blend ----
        self.sim = ALPHA * cf_sim + (1.0 - ALPHA) * content_sim
        np.fill_diagonal(self.sim, 0.0)
        self.user_vectors = {u: M[uidx[u]] for u in users}

    def _content_matrix(self, stores) -> np.ndarray:
        """Build an (items x features) matrix from store attributes.

        Features: multi-hot categories + one-hot price band + one-hot zone +
        scalar quality. Ordered by self.store_ids so rows align with the CF matrix.
        """
        by_id = {s.id: s for s in stores}
        cats = sorted({c for s in stores for c in (s.categories or "").split(",") if c})
        cat_idx = {c: i for i, c in enumerate(cats)}
        zones = sorted({s.zone_id for s in stores if s.zone_id is not None})
        zone_idx = {z: i for i, z in enumerate(zones)}
        n_bands = 3  # budget / mid / premium

        width = len(cats) + n_bands + len(zones) + 1
        X = np.zeros((len(self.store_ids), width))
        for row, sid in enumerate(self.store_ids):
            s = by_id.get(sid)
            if s is None:
                continue
            for c in (s.categories or "").split(","):
                if c in cat_idx:
                    X[row, cat_idx[c]] = 1.0
            price = s.price_min if s.price_min is not None else 400
            band = 0 if price < 250 else 1 if price < 600 else 2
            X[row, len(cats) + band] = 1.0
            if s.zone_id in zone_idx:
                X[row, len(cats) + n_bands + zone_idx[s.zone_id]] = 1.0
            X[row, -1] = (s.experience_score or 3.5) / 5.0
        return X

    def recommend_for_user(self, user_id: int, n: int = 6) -> list[str]:
        if self.sim is None or user_id not in self.user_vectors:
            return []
        vec = self.user_vectors[user_id]
        if vec.sum() == 0:
            return []
        scores = self.sim @ vec
        scores[vec > 0] = -np.inf  # don't recommend already-seen
        order = np.argsort(scores)[::-1][:n]
        return [self.store_ids[i] for i in order if np.isfinite(scores[i]) and scores[i] > 0]

    def similar_stores(self, store_id: str, n: int = 4) -> list[str]:
        if self.sim is None or store_id not in self._idx:
            return []
        i = self._idx[store_id]
        order = np.argsort(self.sim[i])[::-1][:n]
        return [self.store_ids[j] for j in order if self.sim[i][j] > 0]

    def _persist(self, db, n_similar: int = 8, n_recs: int = 12) -> None:
        """Write the top-N similar-store and per-user rec lists to the DB.

        Mirrors the ranking of similar_stores()/recommend_for_user() exactly,
        just materialised for stateless serving. Rewrites both tables wholesale;
        the caller commits.
        """
        from ..models import StoreSimilarity, UserRecommendation
        db.query(StoreSimilarity).delete()
        db.query(UserRecommendation).delete()
        if self.sim is None:
            db.flush()
            return
        for sid in self.store_ids:
            i = self._idx[sid]
            for rank, j in enumerate(np.argsort(self.sim[i])[::-1][:n_similar]):
                sc = float(self.sim[i][j])
                if sc <= 0:
                    break  # ranked desc, so the rest are also <= 0
                db.add(StoreSimilarity(store_id=sid, similar_id=self.store_ids[j],
                                       rank=rank, score=round(sc, 4)))
        for uid, vec in self.user_vectors.items():
            if vec.sum() == 0:
                continue
            scores = self.sim @ vec
            scores[vec > 0] = -np.inf  # don't recommend already-seen
            for rank, j in enumerate(np.argsort(scores)[::-1][:n_recs]):
                sc = scores[j]
                if not np.isfinite(sc) or sc <= 0:
                    break
                db.add(UserRecommendation(user_id=uid, store_id=self.store_ids[j],
                                          rank=rank, score=round(float(sc), 4)))
        db.flush()


# module-level singleton, fit at startup
recommender = Recommender()


def similar_ids(db, store_id: str, n: int = 4) -> list[str]:
    """Serving read: precomputed similar stores from the DB, with an in-memory
    fallback for the window between a fresh boot and the first persisted refit."""
    from ..models import StoreSimilarity
    rows = (db.query(StoreSimilarity)
            .filter(StoreSimilarity.store_id == store_id)
            .order_by(StoreSimilarity.rank).limit(n).all())
    if rows:
        return [r.similar_id for r in rows]
    return recommender.similar_stores(store_id, n)


def user_recs(db, user_id: int, n: int = 6) -> list[str]:
    """Serving read: precomputed per-user recs from the DB, with in-memory fallback."""
    from ..models import UserRecommendation
    rows = (db.query(UserRecommendation)
            .filter(UserRecommendation.user_id == user_id)
            .order_by(UserRecommendation.rank).limit(n).all())
    if rows:
        return [r.store_id for r in rows]
    return recommender.recommend_for_user(user_id, n)

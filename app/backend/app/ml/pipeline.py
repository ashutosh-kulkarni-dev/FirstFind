"""Batch ML pipeline — the one place heavy ML runs.

Phase 4 of the upgrade plan. The web app only ever *reads* precomputed ML
results (experience scores, zones, recommendations); this job computes them.
Run it as a cron/scheduled task (e.g. every few minutes for sentiment/scores,
nightly for zones), or once manually after seeding.

Stages:
  1. Sentiment on reviews not yet scored (sentiment IS NULL) — bulk.
  2. Per-store experience_score (star rating blended with sentiment) + review_count.
  3. Geospatial zones (recluster, rewrite Zone table, reassign store.zone_id).
  4. Recommender refit (hybrid CF + content).

Interactive models stay on the request path by design: single-review sentiment
(POST /reviews) and the chatbot. This job handles bulk/consistency work so no
user ever waits on it.

Run: python -m app.ml.pipeline
"""
import logging

from ..database import SessionLocal
from ..models import Review, Store, Zone
from ..seed import _zone_rows
from . import sentiment as sentiment_ml
from . import zones as zones_ml
from .recommender import recommender

log = logging.getLogger(__name__)


def score_pending_sentiment(db) -> int:
    """Stage 1: score reviews whose sentiment hasn't been computed yet."""
    pending = db.query(Review).filter(Review.sentiment.is_(None)).all()
    for r in pending:
        label, score = sentiment_ml.analyze(r.text or "")
        r.sentiment, r.sentiment_score = label, score
    db.flush()
    return len(pending)


def recompute_store_scores(db) -> int:
    """Stage 2: recompute each store's experience_score and review_count."""
    stores = db.query(Store).all()
    by_store: dict[str, list] = {}
    for r in db.query(Review).all():
        by_store.setdefault(r.store_id, []).append((r.rating, r.sentiment_score or 0.0))
    for s in stores:
        scored = by_store.get(s.id, [])
        s.experience_score = sentiment_ml.experience_score(scored)
        s.review_count = len(scored)
    db.flush()
    return len(stores)


def recompute_zones(db) -> int:
    """Stage 3: recluster stores into zones and rewrite the Zone table."""
    stores = db.query(Store).all()
    zone_dicts = zones_ml.cluster_stores(_zone_rows(stores))

    for s in stores:
        s.zone_id = None
    db.query(Zone).delete()
    db.flush()
    for z in zone_dicts:
        zone = Zone(label=z["label"], center_lat=z["center_lat"],
                    center_lng=z["center_lng"], radius_km=z["radius_km"],
                    store_count=len(z["store_ids"]),
                    avg_score=z["avg_score"], avg_price=z["avg_price"],
                    description="")
        db.add(zone)
        db.flush()
        for sid in z["store_ids"]:
            st = db.get(Store, sid)
            if st:
                st.zone_id = zone.id
    db.flush()
    return len(zone_dicts)


def run_pipeline(db=None) -> dict:
    """Run all stages in one transaction. Returns a summary dict."""
    own = db is None
    db = db or SessionLocal()
    try:
        scored = score_pending_sentiment(db)
        stores = recompute_store_scores(db)
        n_zones = recompute_zones(db)          # before recommender: zone_id feeds content features
        recommender.build(db)
        db.commit()
        summary = {"reviews_scored": scored, "stores_rescored": stores, "zones": n_zones}
        log.info("Pipeline complete: %s", summary)
        return summary
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_pipeline()
    print(f"Pipeline done: {result['reviews_scored']} reviews scored, "
          f"{result['stores_rescored']} stores rescored, {result['zones']} zones.")

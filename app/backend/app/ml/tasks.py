"""Background ML tasks — keep model (re)fitting off the request path.

Phase 1 of the upgrade plan: the collaborative-filtering model used to be
rebuilt synchronously inside GET /stores/{id} and POST /save, so every store
view triggered a full O(users x items^2) refit on the user's latency path.
These helpers run that work *after* the response is sent (FastAPI
BackgroundTasks), each opening its own DB session because the request-scoped
session is already closed by the time a background task runs.
"""
import logging
import threading
import time

from ..database import SessionLocal
from ..models import Review
from . import sentiment as sentiment_ml
from .recommender import recommender

log = logging.getLogger(__name__)

# Debounce rapid interactions (many views in a row) into at most one rebuild
# per interval. Saves pass force=True — a save is a strong personalization
# signal we want reflected promptly.
_lock = threading.Lock()
_last_build = 0.0
MIN_INTERVAL = 15.0  # seconds


def build_recommender() -> None:
    """(Re)fit the recommender in its own session and persist the results.

    The single place the fit's session lifecycle lives — called unconditionally
    at startup and (debounced) by refit_recommender. `recommender.build` fits the
    in-memory matrix AND writes the precomputed similar/rec tables; we commit.
    """
    db = SessionLocal()
    try:
        recommender.build(db)
        db.commit()
    finally:
        db.close()


def refit_recommender(force: bool = False) -> None:
    """Rebuild the CF model in the background, debounced unless forced."""
    global _last_build
    with _lock:
        now = time.time()
        if not force and now - _last_build < MIN_INTERVAL:
            return
        _last_build = now
        build_recommender()


def score_review(review_id: int) -> None:
    """Score one review's sentiment via the HF API, then refresh its store's score.

    Runs off the request path (FastAPI BackgroundTask) with its own DB session, so
    POST /reviews returns immediately and the store's sentiment meter updates a few
    seconds later. Never raises — a background failure must not crash the worker; the
    batch pipeline re-scores anything left with sentiment IS NULL.
    """
    db = SessionLocal()
    try:
        review = db.get(Review, review_id)
        if review is None:
            return
        label, score = sentiment_ml.analyze(review.text or "")
        review.sentiment, review.sentiment_score = label, score
        # Recompute the store's experience_score + review_count over all its reviews.
        store = review.store
        scored = [(r.rating, r.sentiment_score or 0.0) for r in
                  db.query(Review).filter(Review.store_id == review.store_id).all()]
        store.experience_score = sentiment_ml.experience_score(scored)
        store.review_count = len(scored)
        db.commit()
    except Exception as e:
        log.warning("score_review(%s) failed: %s", review_id, e)
        db.rollback()
    finally:
        db.close()

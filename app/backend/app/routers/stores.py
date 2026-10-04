import datetime as dt
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user, get_optional_user
from ..database import get_db
from ..ml.recommender import similar_ids
from ..ml.tasks import refit_recommender
from ..models import Interaction, Review, Store, StoreSimilarity, User
from ..schemas import ReviewIn
from ..utils import (STORE_HAS_COORDS, has_coords, haversine_km, is_open_now,
                     sentiment_summary, store_to_dict)

router = APIRouter(prefix="/api/stores", tags=["stores"])

VIEW_DEDUP_HOURS = 24


def stores_within(db: Session, lat: float, lng: float, radius_km: float) -> list:
    """Return all visible stores within radius_km of (lat, lng), sorted by distance.

    Shared by /nearby and find_cluster so the radius filter is never duplicated.
    """
    out = []
    for s in db.query(Store).filter(*STORE_HAS_COORDS).all():
        d = haversine_km(lat, lng, s.lat, s.lng)
        if d <= radius_km:
            out.append((d, s))
    out.sort(key=lambda x: x[0])
    return [s for _, s in out]


@router.get("")
def list_stores(area: Optional[str] = None, category: Optional[str] = None,
                price_max: Optional[int] = None, open_now: Optional[bool] = None,
                q: Optional[str] = None, db: Session = Depends(get_db)):
    # Only stores with real coordinates are shown to users (see STORE_HAS_COORDS).
    query = db.query(Store).filter(*STORE_HAS_COORDS)
    if area:
        query = query.filter(Store.area == area)
    if category:
        query = query.filter(Store.categories.contains(category))
    if price_max:
        query = query.filter(Store.price_min.isnot(None), Store.price_min <= price_max)
    if q:
        # Search matches a store's name or its location (area / raw locality).
        like = f"%{q}%"
        query = query.filter(or_(
            Store.name.ilike(like),
            Store.area.ilike(like),
            Store.locality_raw.ilike(like),
        ))
    stores = query.all()
    if open_now:
        stores = [s for s in stores if is_open_now(s)]
    stores.sort(key=lambda s: (s.experience_score or 0), reverse=True)
    return {"count": len(stores), "stores": [store_to_dict(s) for s in stores]}


@router.get("/areas")
def list_areas(db: Session = Depends(get_db)):
    return sorted(a[0] for a in
                  db.query(Store.area).filter(*STORE_HAS_COORDS).distinct().all() if a[0])


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """Distinct real categories across all stores (for the Explore filter).

    Categories are stored comma-joined; blank when the source didn't provide
    one, so those stores contribute nothing here.
    """
    cats = set()
    for (raw,) in db.query(Store.categories).filter(*STORE_HAS_COORDS).distinct().all():
        cats.update(c.strip() for c in (raw or "").split(",") if c.strip())
    return sorted(cats)


@router.get("/areas/coords")
def area_coords(db: Session = Depends(get_db)):
    """Return centroid coordinates for every area and distinct locality_raw.

    Emits both area-level and sub-locality centroids so Mode B can use any
    named place — including small pockets inside a zone — as a start point.
    Shape: [{name, kind: "area"|"locality", lat, lng, count}]
    """
    from collections import defaultdict
    area_pts: dict = defaultdict(list)
    locality_pts: dict = defaultdict(list)

    for s in db.query(Store).filter(*STORE_HAS_COORDS).all():
        if s.area:
            area_pts[s.area].append((s.lat, s.lng))
        if s.locality_raw:
            locality_pts[s.locality_raw].append((s.lat, s.lng))

    results = []
    for name, pts in area_pts.items():
        results.append({
            "name": name,
            "kind": "area",
            "lat": sum(p[0] for p in pts) / len(pts),
            "lng": sum(p[1] for p in pts) / len(pts),
            "count": len(pts),
        })
    for name, pts in locality_pts.items():
        results.append({
            "name": name,
            "kind": "locality",
            "lat": sum(p[0] for p in pts) / len(pts),
            "lng": sum(p[1] for p in pts) / len(pts),
            "count": len(pts),
        })

    results.sort(key=lambda x: (-x["count"], x["name"]))
    return results


@router.get("/nearby")
def nearby(lat: float, lng: float, radius_km: float = 5.0,
           db: Session = Depends(get_db)):
    stores = stores_within(db, lat, lng, radius_km)
    return {"count": len(stores), "stores": [store_to_dict(s, lat, lng) for s in stores]}


@router.get("/{store_id}")
def store_detail(store_id: str, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db),
                 user: Optional[User] = Depends(get_optional_user)):
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    # Hidden (no-coordinate) stores exist in the DB for manual pinning but are
    # not exposed to users — treat their detail page as not found.
    if not has_coords(store):
        raise HTTPException(404, "Store not found")
    # Log a view interaction for personalization, but only once per user/store
    # per VIEW_DEDUP_HOURS so a page refresh doesn't inflate the CF signal. The
    # CF refit runs in the background (debounced), never on the request path.
    if user:
        since = dt.datetime.utcnow() - dt.timedelta(hours=VIEW_DEDUP_HOURS)
        already_viewed = (db.query(Interaction.id)
                          .filter(Interaction.user_id == user.id,
                                  Interaction.store_id == store.id,
                                  Interaction.kind == "view",
                                  Interaction.created_at >= since)
                          .first())
        if not already_viewed:
            db.add(Interaction(user_id=user.id, store_id=store.id, kind="view"))
            db.commit()
            background_tasks.add_task(refit_recommender)

    # joinedload(user) so rendering r.user.name below is one query, not N+1.
    reviews = (db.query(Review).filter(Review.store_id == store_id)
               .options(joinedload(Review.user))
               .order_by(Review.created_at.desc()).all())
    summary = sentiment_summary(reviews)
    # Fetch similar stores with their precomputed similarity score so the frontend
    # can show "X% match". Query StoreSimilarity directly to get the score in one
    # pass rather than calling similar_ids() then re-fetching the rows.
    similar = []
    sim_rows = (db.query(StoreSimilarity)
                .filter(StoreSimilarity.store_id == store_id)
                .order_by(StoreSimilarity.rank)
                .limit(4).all())
    for row in sim_rows:
        s = db.get(Store, row.similar_id)
        if has_coords(s):
            d = store_to_dict(s)
            d["match_pct"] = round(float(row.score) * 100)
            similar.append(d)
    # Fall back to in-memory recommender if DB has no precomputed rows yet.
    if not similar:
        for sid in similar_ids(db, store_id):
            s = db.get(Store, sid)
            if has_coords(s):
                similar.append(store_to_dict(s))

    d = store_to_dict(store)
    d["reviews"] = [{
        "id": r.id, "user_name": r.user.name, "rating": r.rating, "text": r.text,
        "sentiment": r.sentiment,
        "created_at": r.created_at.strftime("%d %b %Y"),
    } for r in reviews]
    d["similar"] = similar
    d["sentiment_summary"] = summary
    return d


@router.post("/{store_id}/reviews")
def add_review(store_id: str, body: ReviewIn, background_tasks: BackgroundTasks,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    from ..ml.tasks import score_review
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    # Save the review immediately with sentiment pending; scoring happens off the
    # request path via the HF Inference API. The store's experience_score /
    # review_count and this review's sentiment are updated by the background task
    # a few seconds later.
    review = Review(store_id=store_id, user_id=user.id, rating=body.rating,
                    text=body.text, sentiment=None, sentiment_score=None)
    db.add(review)
    db.commit()
    background_tasks.add_task(score_review, review.id)
    return {"ok": True, "sentiment": "pending"}


@router.post("/{store_id}/save")
def save_store(store_id: str, background_tasks: BackgroundTasks,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    if not db.get(Store, store_id):
        raise HTTPException(404, "Store not found")
    db.add(Interaction(user_id=user.id, store_id=store_id, kind="save"))
    db.commit()
    # A save is a strong signal — refit promptly, but still off the request
    # path (force=True skips the debounce so recs update within moments).
    background_tasks.add_task(refit_recommender, force=True)
    return {"ok": True}

"""Admin API: edit, hide, add and delete stores; hide or delete reviews; the
"needs attention" list; the change log; CSV export.

Every route requires an admin account (require_admin, checked against the
database on each request). Every change writes one AdminAudit row.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections import Counter
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..common.serializers import REVIEW_VISIBLE, store_to_dict
from ..data.importer import delete_stores
from ..data.tags import STORE_TYPE_LABELS, TAG_LABELS, split_tags
from ..database import get_db
from ..ml import sentiment as sentiment_ml
from ..ml.tasks import refit_recommender
from ..models import AdminAudit, Review, Store, User

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

class StoreFields(BaseModel):
    """Every editable store field. On PATCH only the fields sent are changed."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    area: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, max_length=80)
    locality_raw: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=300)
    lat: Optional[float] = Field(None, ge=12.6, le=13.4)     # greater Bengaluru
    lng: Optional[float] = Field(None, ge=77.3, le=77.9)
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    timing_note: Optional[str] = Field(None, max_length=200)
    closed_days: Optional[list[str]] = None
    notes: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=30)
    instagram: Optional[str] = Field(None, max_length=120)
    categories: Optional[list[str]] = None
    store_type: Optional[str] = None
    tags: Optional[list[str]] = None
    price_min: Optional[int] = Field(None, ge=0, le=100000)
    price_max: Optional[int] = Field(None, ge=0, le=100000)
    price_estimated: Optional[bool] = None
    description: Optional[str] = Field(None, max_length=1000)
    is_active: Optional[bool] = None

    @field_validator("open_time", "close_time")
    @classmethod
    def _time(_cls, v):
        if v in (None, ""):
            return None
        if not _TIME_RE.match(v):
            raise ValueError("use 24-hour HH:MM, e.g. 11:00")
        return v

    @field_validator("store_type")
    @classmethod
    def _kind(_cls, v):
        if v is not None and v not in STORE_TYPE_LABELS:
            raise ValueError(f"must be one of {sorted(STORE_TYPE_LABELS)}")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(_cls, v):
        if v is not None:
            bad = [t for t in v if t not in TAG_LABELS]
            if bad:
                raise ValueError(f"unknown tags: {bad}")
        return v

    @field_validator("closed_days")
    @classmethod
    def _days(_cls, v):
        if v is not None:
            bad = [d for d in v if d not in _DAYS]
            if bad:
                raise ValueError(f"unknown days: {bad}")
        return v

    @field_validator("categories")
    @classmethod
    def _cats(_cls, v):
        if v is not None:
            v = [c.strip() for c in v if c.strip()]
            if any("," in c for c in v):
                raise ValueError("a category may not contain a comma")
        return v


class StoreCreate(StoreFields):
    name: str = Field(..., min_length=1, max_length=200)
    area: str = Field(..., min_length=1, max_length=100)


class ReviewPatch(BaseModel):
    is_hidden: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LIST_FIELDS = {"closed_days", "categories", "tags"}


def _column_value(field: str, value):
    """API value -> what the Store column holds."""
    if field in _LIST_FIELDS:
        return ",".join(value) if value else ""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _json_safe(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    return v


def _audit(db: Session, admin: User, action: str, entity: str, entity_id: str,
           changes: Optional[dict] = None) -> None:
    db.add(AdminAudit(
        user_id=admin.id, user_email=admin.email, action=action, entity=entity,
        entity_id=str(entity_id),
        changes=json.dumps({k: _json_safe(v) for k, v in (changes or {}).items()},
                           default=str, ensure_ascii=False) if changes else None,
    ))


def _snapshot(obj, fields) -> dict:
    return {f: _json_safe(getattr(obj, f)) for f in fields}


_STORE_COLUMNS = [c.name for c in Store.__table__.columns]
_REVIEW_COLUMNS = [c.name for c in Review.__table__.columns]


def _admin_store(store: Store) -> dict:
    """The public store shape plus the fields only admins see."""
    d = store_to_dict(store)
    d.update({
        "city": store.city,
        "locality_raw": store.locality_raw,
        "is_active": store.is_active is not False,
        "created_via": store.created_via or "csv",
        "admin_edited_at": _json_safe(store.admin_edited_at),
        "google_status": store.google_status,
        "geocode_precision": store.geocode_precision,
        "tags_source": store.tags_source,
    })
    return d


def _get_store(db: Session, store_id: str) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise HTTPException(404, "Store not found")
    return store


def _apply(store: Store, fields: dict) -> dict:
    """Write `fields` onto `store`; return {field: [before, after]} for what changed."""
    changes = {}
    for field, value in fields.items():
        new = _column_value(field, value)
        old = getattr(store, field)
        if field == "is_active":
            old = old is not False
        if new != old:
            changes[field] = [_json_safe(old), _json_safe(new)]
            setattr(store, field, new)
    if "description" in changes:
        store.description_source = "admin" if store.description else None
    if "tags" in changes:
        store.tags_source = "admin"
    if "lat" in changes or "lng" in changes:
        store.geocode_precision = "admin" if store.lat is not None else None
    return changes


def _check_pin_and_price(store: Store) -> None:
    if (store.lat is None) != (store.lng is None):
        raise HTTPException(422, "Set both latitude and longitude, or neither")
    if (store.price_min is not None and store.price_max is not None
            and store.price_min > store.price_max):
        raise HTTPException(422, "Lowest price is above the highest price")


def _next_store_id(db: Session) -> str:
    nums = [int(m.group(1)) for (sid,) in db.query(Store.id)
            if (m := re.fullmatch(r"blr-(\d+)", sid or ""))]
    return f"blr-{(max(nums) + 1 if nums else 1):04d}"


def _rescore(db: Session, store_id: str) -> None:
    """Recompute a store's score and review count from its visible reviews."""
    store = db.get(Store, store_id)
    if store is None:
        return
    scored = [sentiment_ml.review_tuple(r) for r in
              db.query(Review).filter(Review.store_id == store_id, REVIEW_VISIBLE)]
    store.experience_score = sentiment_ml.experience_score(scored, sentiment_ml.score_prior(store))
    store.review_count = len(scored)


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

@router.get("/meta")
def meta():
    """Choices for the edit form."""
    return {
        "store_types": [{"value": k, "label": v} for k, v in STORE_TYPE_LABELS.items()],
        "tags": [{"value": k, "label": v} for k, v in TAG_LABELS.items()],
        "days": sorted(_DAYS, key=["Monday", "Tuesday", "Wednesday", "Thursday",
                                   "Friday", "Saturday", "Sunday"].index),
    }


@router.get("/stores")
def list_stores(q: Optional[str] = None,
                status: Literal["all", "visible", "hidden"] = "all",
                db: Session = Depends(get_db)):
    query = db.query(Store)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Store.name.ilike(like), Store.id.ilike(like),
                                 Store.area.ilike(like), Store.locality_raw.ilike(like)))
    if status == "visible":
        query = query.filter(Store.is_active.isnot(False))
    elif status == "hidden":
        query = query.filter(Store.is_active.is_(False))
    stores = query.order_by(Store.id).all()
    return {"count": len(stores), "stores": [_admin_store(s) for s in stores]}


@router.get("/stores/{store_id}")
def get_store(store_id: str, db: Session = Depends(get_db)):
    store = _get_store(db, store_id)
    d = _admin_store(store)
    reviews = (db.query(Review).filter(Review.store_id == store_id)
               .order_by(Review.created_at.desc()).all())
    d["reviews"] = [_admin_review(r, store) for r in reviews]
    return d


@router.post("/stores", status_code=201)
def create_store(body: StoreCreate, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    store = Store(id=_next_store_id(db), created_via="admin",
                  admin_edited_at=dt.datetime.utcnow(),
                  experience_score=None, review_count=0, is_active=True)
    _apply(store, body.model_dump(exclude_unset=True))
    store.store_type = store.store_type or "thrift"
    store.city = store.city or "Bengaluru"
    _check_pin_and_price(store)
    db.add(store)
    db.flush()
    _audit(db, admin, "create", "store", store.id, _snapshot(store, _STORE_COLUMNS))
    db.commit()
    background_tasks.add_task(refit_recommender, force=True)
    return _admin_store(store)


@router.patch("/stores/{store_id}")
def update_store(store_id: str, body: StoreFields, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    store = _get_store(db, store_id)
    fields = body.model_dump(exclude_unset=True)
    for required in ("name", "area"):
        if required in fields and not (fields[required] or "").strip():
            raise HTTPException(422, f"{required} cannot be empty")
    changes = _apply(store, fields)
    if not changes:
        return _admin_store(store)
    _check_pin_and_price(store)
    store.admin_edited_at = dt.datetime.utcnow()
    if set(changes) == {"is_active"}:
        action = "unhide" if store.is_active else "hide"
    else:
        action = "update"
    _audit(db, admin, action, "store", store.id, changes)
    db.commit()
    background_tasks.add_task(refit_recommender, force=True)
    return _admin_store(store)


@router.delete("/stores/{store_id}")
def delete_store(store_id: str, background_tasks: BackgroundTasks,
                 confirm: str = Query(..., description="must repeat the store id"),
                 db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Permanent. The caller must pass ?confirm=<store id> so a stray request
    cannot delete a store."""
    store = _get_store(db, store_id)
    if confirm != store_id:
        raise HTTPException(400, "confirm must equal the store id")
    snapshot = _snapshot(store, _STORE_COLUMNS)
    reviews_removed = delete_stores(db, [store_id])
    snapshot["reviews_removed"] = reviews_removed
    _audit(db, admin, "delete", "store", store_id, snapshot)
    db.commit()
    background_tasks.add_task(refit_recommender, force=True)
    return {"ok": True, "reviews_removed": reviews_removed}


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def _admin_review(r: Review, store: Optional[Store] = None) -> dict:
    store = store or r.store
    return {
        "id": r.id, "store_id": r.store_id, "store_name": store.name if store else None,
        "rating": r.rating, "text": r.text, "source": r.source or "app",
        "author": r.author_name or (r.user.name if r.user else None),
        "sentiment": r.sentiment, "is_hidden": bool(r.is_hidden),
        "created_at": _json_safe(r.created_at),
    }


@router.get("/reviews")
def list_reviews(q: Optional[str] = None, store_id: Optional[str] = None,
                 status: Literal["all", "visible", "hidden"] = "all",
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)):
    query = db.query(Review)
    if store_id:
        query = query.filter(Review.store_id == store_id)
    if q:
        query = query.filter(Review.text.ilike(f"%{q.strip()}%"))
    if status == "visible":
        query = query.filter(REVIEW_VISIBLE)
    elif status == "hidden":
        query = query.filter(Review.is_hidden.is_(True))
    total = query.count()
    rows = query.order_by(Review.created_at.desc(), Review.id.desc()).offset(offset).limit(limit).all()
    return {"count": total, "reviews": [_admin_review(r) for r in rows]}


@router.patch("/reviews/{review_id}")
def set_review_hidden(review_id: int, body: ReviewPatch,
                      db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "Review not found")
    if bool(review.is_hidden) != body.is_hidden:
        review.is_hidden = body.is_hidden
        db.flush()
        _rescore(db, review.store_id)
        _audit(db, admin, "hide" if body.is_hidden else "unhide", "review", review.id,
               {"store_id": review.store_id, "text": (review.text or "")[:200]})
        db.commit()
    return _admin_review(review)


@router.delete("/reviews/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db),
                  admin: User = Depends(require_admin)):
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "Review not found")
    store_id = review.store_id
    snapshot = _snapshot(review, _REVIEW_COLUMNS)
    db.delete(review)
    db.flush()
    _rescore(db, store_id)
    _audit(db, admin, "delete", "review", review_id, snapshot)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Needs attention
# ---------------------------------------------------------------------------

# Names that describe a kind of shop or a place, not one particular store.
_GENERIC_NAMES = {"thrift store", "thrift shop", "thrift", "clothing store", "clothes shop",
                  "store", "shop", "boutique", "second hand store", "vintage store",
                  "used clothes", "readymade garments", "garments", "fashion store"}
# A short name that is only a place ("Raheja Arcade", "Tibetan Market"). Names
# with a separator ("Fabindia, HSR Layout", "Rareism - Brigade Road") are a
# brand plus its branch and are fine.
_PLACE_WORDS_RE = re.compile(r"\b(market|arcade|bazaa?r|complex|mall|plaza)\s*$", re.I)
_BRANCH_SEPARATOR_RE = re.compile(r"[,|]|\s[-–]\s")


def placeholder_reason(name: str) -> Optional[str]:
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    if not re.search(r"[a-z]", n):
        return "Name has no letters"
    if n in _GENERIC_NAMES:
        return "Generic name, not a store's own name"
    if _PLACE_WORDS_RE.search(n) and not _BRANCH_SEPARATOR_RE.search(n) and len(n.split()) <= 4:
        return "Looks like a market or street, not a store"
    return None


@router.get("/attention")
def needs_attention(db: Session = Depends(get_db)):
    stores = db.query(Store).order_by(Store.id).all()
    dupes = Counter((s.name or "").strip().lower() + "|" + (s.area or "").lower()
                    for s in stores if s.is_active is not False)
    items = []
    for s in stores:
        reasons = []
        if s.google_status == "not_found":
            reasons.append({"code": "not_on_google", "label": "Google could not find it"})
        if s.lat is None or s.lng is None:
            reasons.append({"code": "no_pin", "label": "No map pin"})
        why = placeholder_reason(s.name)
        if why:
            reasons.append({"code": "placeholder_name", "label": why})
        if s.is_active is not False and dupes[(s.name or "").strip().lower() + "|" + (s.area or "").lower()] > 1:
            reasons.append({"code": "duplicate", "label": "Same name in the same area"})
        if reasons:
            items.append({"store": _admin_store(s), "reasons": reasons})
    counts = Counter(r["code"] for it in items for r in it["reasons"])
    return {"count": len(items), "by_reason": dict(counts), "items": items}


# ---------------------------------------------------------------------------
# Change log and export
# ---------------------------------------------------------------------------

@router.get("/audit")
def audit_log(entity: Optional[str] = None, entity_id: Optional[str] = None,
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db)):
    query = db.query(AdminAudit)
    if entity:
        query = query.filter(AdminAudit.entity == entity)
    if entity_id:
        query = query.filter(AdminAudit.entity_id == entity_id)
    total = query.count()
    rows = (query.order_by(AdminAudit.created_at.desc(), AdminAudit.id.desc())
            .offset(offset).limit(limit).all())
    return {"count": total, "entries": [{
        "id": a.id, "user_email": a.user_email, "action": a.action, "entity": a.entity,
        "entity_id": a.entity_id, "changes": json.loads(a.changes) if a.changes else None,
        "created_at": _json_safe(a.created_at),
    } for a in rows]}


# Same columns as data/import/stores.csv (so an export can be re-imported),
# then the admin-only fields.
_EXPORT_COLUMNS = ["id", "name", "locality_raw", "city", "instagram", "phone",
                   "open_time", "close_time", "timing_note", "notes", "lat", "lng",
                   "geocode_precision", "price_min", "price_max", "categories",
                   "store_type", "rating", "review_count", "address", "google_place_id",
                   "description", "area", "tags", "closed_days", "is_active", "created_via",
                   "google_status", "experience_score", "app_review_count"]


def _export_row(s: Store) -> list:
    cats = [c for c in (s.categories or "").split(",") if c]
    return [s.id, s.name, s.locality_raw or "", s.city or "", s.instagram or "", s.phone or "",
            s.open_time or "", s.close_time or "", s.timing_note or "", s.notes or "",
            "" if s.lat is None else s.lat, "" if s.lng is None else s.lng,
            s.geocode_precision or "", "" if s.price_min is None else s.price_min,
            "" if s.price_max is None else s.price_max,
            str(cats) if cats else "[]", s.store_type or "thrift",
            "" if s.google_rating is None else s.google_rating,
            "" if s.google_review_count is None else s.google_review_count,
            s.address or "", s.google_place_id or "", s.description or "", s.area or "",
            ",".join(split_tags(s.tags)), s.closed_days or "",
            "true" if s.is_active is not False else "false", s.created_via or "csv",
            s.google_status or "",
            "" if s.experience_score is None else round(s.experience_score, 2),
            s.review_count or 0]


@router.get("/export/stores.csv")
def export_stores(db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_EXPORT_COLUMNS)
    for s in db.query(Store).order_by(Store.id):
        w.writerow(_export_row(s))
    stamp = dt.datetime.utcnow().strftime("%Y-%m-%d")
    return StreamingResponse(
        iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="firstfind-stores-{stamp}.csv"'})


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Headline counts for the top of the admin page."""
    total = db.query(func.count(Store.id)).scalar()
    hidden = db.query(func.count(Store.id)).filter(Store.is_active.is_(False)).scalar()
    no_pin = db.query(func.count(Store.id)).filter(or_(Store.lat.is_(None), Store.lng.is_(None))).scalar()
    reviews = db.query(func.count(Review.id)).scalar()
    hidden_reviews = db.query(func.count(Review.id)).filter(Review.is_hidden.is_(True)).scalar()
    return {"stores": total, "hidden_stores": hidden, "no_pin": no_pin,
            "reviews": reviews, "hidden_reviews": hidden_reviews}

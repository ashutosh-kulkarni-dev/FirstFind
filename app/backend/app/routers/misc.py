"""Zones, recommendations, chat, health."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_optional_user
from ..chat import engine as chat_engine
from ..database import get_db
from ..ml.recommender import user_recs
from ..models import Store, User, Zone
from ..schemas import ChatIn
from ..utils import STORE_HAS_COORDS, has_coords, store_to_dict, zone_to_dict

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "thriftfind-api"}


@router.get("/zones")
def zones(db: Session = Depends(get_db)):
    out = []
    for z in db.query(Zone).all():
        top = (db.query(Store).filter(Store.zone_id == z.id, *STORE_HAS_COORDS)
               .order_by(Store.experience_score.desc()).limit(3).all())
        out.append(zone_to_dict(z, stores=top))
    return out


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db),
                    user: Optional[User] = Depends(get_optional_user)):
    personalized = False
    stores = []
    if user:
        ids = user_recs(db, user.id)
        stores = [db.get(Store, sid) for sid in ids]
        stores = [s for s in stores if has_coords(s)]   # never surface hidden stores
        personalized = bool(stores)
    if not stores:  # cold start / guest fallback
        # Scored stores surface first once real reviews exist; until then this
        # returns real stores (unscored) rather than an empty list. MySQL sorts
        # NULLs last under DESC, so no explicit score filter is needed.
        stores = (db.query(Store).filter(*STORE_HAS_COORDS)
                  .order_by(Store.experience_score.desc()).limit(6).all())
    return {"personalized": personalized,
            "stores": [store_to_dict(s) for s in stores]}


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db),
         user: Optional[User] = Depends(get_optional_user)):
    origin = (body.origin.lat, body.origin.lng) if body.origin else None
    result = chat_engine.respond(body.message, db, user, body.session_id, origin=origin)
    # Persist the turn for logged-in users only; guests stay ephemeral.
    # Import lazily so history stays an optional, removable module.
    if user:
        from ..chat.history import record_turn
        record_turn(db, user, body.session_id, body.message, result)
    return result

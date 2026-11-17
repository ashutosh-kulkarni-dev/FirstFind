"""Zones, recommendations, chat, health."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_optional_user
from ..chat import engine as chat_engine
from ..database import get_db
from ..ml.recommender import chain_key, user_rec_rows
from ..models import Store, User, Zone
from ..schemas import ChatIn
from ..common.serializers import STORE_HAS_COORDS, has_coords, store_to_dict, zone_to_dict

router = APIRouter(prefix="/api", tags=["misc"])

# Best score first. Postgres (production) sorts NULL *first* under DESC, which
# put unscored stores at the top of "Top rated"; sort the NULLs last explicitly
# in a way every database understands, then fall back to the Google rating.
BEST_FIRST = (Store.experience_score.is_(None), Store.experience_score.desc(),
              Store.google_rating.is_(None), Store.google_rating.desc(), Store.id)


@router.get("/health")
def health():
    return {"status": "ok", "service": "firstfind-api"}


@router.get("/zones")
def zones(db: Session = Depends(get_db)):
    out = []
    for z in db.query(Zone).all():
        top = (db.query(Store).filter(Store.zone_id == z.id, *STORE_HAS_COORDS)
               .order_by(*BEST_FIRST).limit(3).all())
        out.append(zone_to_dict(z, stores=top))
    return out


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db),
                    user: Optional[User] = Depends(get_optional_user)):
    if user:
        picks = []
        for sid, reason in user_rec_rows(db, user.id):
            s = db.get(Store, sid)
            if has_coords(s):                        # never surface hidden stores
                d = store_to_dict(s)
                d["reason"] = reason
                picks.append(d)
        if picks:
            return {"personalized": True, "stores": picks}
    # Cold start / guest: top rated (scored stores first, so never empty), with
    # at most one branch of any chain.
    stores, chains = [], set()
    for s in db.query(Store).filter(*STORE_HAS_COORDS).order_by(*BEST_FIRST).limit(60):
        key = chain_key(s.name)
        if key in chains:
            continue
        chains.add(key)
        stores.append(s)
        if len(stores) == 6:
            break
    return {"personalized": False, "stores": [store_to_dict(s) for s in stores]}


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

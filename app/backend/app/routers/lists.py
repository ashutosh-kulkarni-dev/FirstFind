from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import SavedList, SavedListItem, Store, User
from ..schemas import SavedListIn, SavedListPatch
from ..utils import has_coords, store_to_dict

router = APIRouter(prefix="/api/lists", tags=["lists"])


@router.post("", status_code=201)
def create_list(body: SavedListIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    name = body.name.strip()
    if db.query(SavedList).filter(SavedList.user_id == user.id,
                                  SavedList.name == name).first():
        raise HTTPException(409, f'You already have a list named "{name}"')

    lst = SavedList(user_id=user.id, name=name,
                    center_lat=body.center_lat, center_lng=body.center_lng,
                    radius_km=body.radius_km, source_label=body.source_label)
    db.add(lst)
    db.flush()   # get lst.id before adding items

    for pos, sid in enumerate(body.store_ids):
        if db.get(Store, sid):   # only attach stores that exist
            db.add(SavedListItem(list_id=lst.id, store_id=sid, position=pos))

    db.commit()
    db.refresh(lst)
    return _list_summary(lst)


@router.get("")
def list_lists(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    rows = (db.query(SavedList)
            .filter(SavedList.user_id == user.id)
            .order_by(SavedList.created_at.desc())
            .all())
    return [_list_summary(lst) for lst in rows]


@router.get("/{list_id}")
def get_list(list_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    lst = _owned_or_404(db, user, list_id)
    stores = []
    for item in lst.items:
        s = db.get(Store, item.store_id)
        if s and has_coords(s):
            stores.append(store_to_dict(s))
    return {**_list_summary(lst), "stores": stores,
            "center_lat": lst.center_lat, "center_lng": lst.center_lng,
            "radius_km": lst.radius_km}


@router.patch("/{list_id}")
def update_list(list_id: int, body: SavedListPatch,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lst = _owned_or_404(db, user, list_id)

    if body.name is not None:
        name = body.name.strip()
        conflict = (db.query(SavedList)
                    .filter(SavedList.user_id == user.id,
                            SavedList.name == name,
                            SavedList.id != list_id)
                    .first())
        if conflict:
            raise HTTPException(409, f'You already have a list named "{name}"')
        lst.name = name

    existing_ids = {item.store_id for item in lst.items}
    max_pos = max((item.position for item in lst.items), default=-1)

    for sid in body.add_ids:
        if sid not in existing_ids and db.get(Store, sid):
            max_pos += 1
            db.add(SavedListItem(list_id=lst.id, store_id=sid, position=max_pos))

    for sid in body.remove_ids:
        for item in lst.items:
            if item.store_id == sid:
                db.delete(item)
                break

    db.commit()
    db.refresh(lst)
    return _list_summary(lst)


@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    lst = _owned_or_404(db, user, list_id)
    db.delete(lst)
    db.commit()


# ---------------------------------------------------------------------------

def _owned_or_404(db: Session, user: User, list_id: int) -> SavedList:
    lst = db.get(SavedList, list_id)
    if lst is None or lst.user_id != user.id:
        raise HTTPException(404, "List not found")
    return lst


def _list_summary(lst: SavedList) -> dict:
    return {
        "id": lst.id,
        "name": lst.name,
        "store_count": len(lst.items),
        "source_label": lst.source_label,
        "created_at": lst.created_at.isoformat(),
    }

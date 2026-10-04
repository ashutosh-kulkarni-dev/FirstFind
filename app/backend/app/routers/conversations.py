from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..chat.history import claim_session
from ..database import get_db
from ..models import Conversation, User

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ---- schemas (local — not shared, these are conversation-specific) ----------

class TurnIn(BaseModel):
    role: str           # "user" | "assistant"
    text: str
    meta: Optional[dict] = None


class ClaimIn(BaseModel):
    session_id: str
    turns: List[TurnIn] = []


# ---- endpoints --------------------------------------------------------------

@router.get("")
def list_conversations(db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    convs = (db.query(Conversation)
             .filter(Conversation.user_id == user.id)
             .order_by(Conversation.updated_at.desc())
             .limit(50)
             .all())
    return [
        {
            "id": c.id,
            "title": c.title or "Untitled conversation",
            "message_count": len(c.messages),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in convs
    ]


@router.get("/{conv_id}")
def get_conversation(conv_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    conv = _owned_or_404(db, user, conv_id)
    return {
        "id": conv.id,
        "title": conv.title or "Untitled conversation",
        "created_at": conv.created_at.isoformat(),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "text": m.text,
                "meta": m.meta,   # raw JSON string; frontend parses
                "created_at": m.created_at.isoformat(),
            }
            for m in conv.messages
        ],
    }


@router.delete("/{conv_id}", status_code=204)
def delete_conversation(conv_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    conv = _owned_or_404(db, user, conv_id)
    db.delete(conv)
    db.commit()


@router.post("/claim")
def claim(body: ClaimIn, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Attach a guest transcript to the user's history (idempotent)."""
    turns = [t.model_dump() for t in body.turns]
    conv = claim_session(db, user, body.session_id, turns)
    if conv is None:
        raise HTTPException(500, "Could not claim session")
    return {"id": conv.id, "title": conv.title}


# ---------------------------------------------------------------------------

def _owned_or_404(db: Session, user: User, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return conv

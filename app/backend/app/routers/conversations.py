from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..chat.history import claim_session
from ..database import get_db
from ..models import ChatMessage, Conversation, User
from ..schemas import SessionId

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ---- schemas (local — not shared, these are conversation-specific) ----------

class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)
    meta: Optional[dict] = None


class ClaimIn(BaseModel):
    session_id: SessionId
    # A guest transcript is short; the cap stops one request storing megabytes.
    turns: list[TurnIn] = Field(default_factory=list, max_length=100)


# ---- endpoints --------------------------------------------------------------

@router.get("")
def list_conversations(db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    # Count messages in SQL: len(c.messages) loaded every message of all 50
    # conversations just to count them.
    counts = (db.query(ChatMessage.conversation_id, func.count(ChatMessage.id))
              .group_by(ChatMessage.conversation_id).subquery())
    rows = (db.query(Conversation, func.coalesce(counts.c[1], 0))
            .outerjoin(counts, counts.c.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
            .all())
    return [
        {
            "id": c.id,
            "title": c.title or "Untitled conversation",
            "message_count": n,
            "updated_at": c.updated_at.isoformat(),
        }
        for c, n in rows
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

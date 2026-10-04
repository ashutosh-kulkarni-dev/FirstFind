"""Chat history persistence — layered outside the engine, not inside it.

The engine (engine.py::respond) is pure: message in, result dict out.
History is written by the /api/chat route after it has the result, only for
authenticated users. Guests stay ephemeral; their turns become durable only
if they later claim the session.

Public interface:
    record_turn(db, user, session_id, user_text, result_dict) -> None
    claim_session(db, user, session_id, turns) -> Conversation | None
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from ..models import ChatMessage, Conversation, User


def record_turn(
    db: Session,
    user: User,
    session_id: Optional[str],
    user_text: str,
    result: dict,
) -> None:
    """Persist one user+assistant turn for a logged-in user.

    Finds or creates a Conversation keyed by (user_id, session_id), then
    appends two ChatMessage rows. Commits inline — the route already owns
    the session lifecycle, but this is a fire-and-forget write that must not
    block the response; any exception is swallowed so a history write failure
    never breaks the chat.
    """
    try:
        conv = _get_or_create_conversation(db, user, session_id, user_text)
        db.add(ChatMessage(conversation_id=conv.id, role="user", text=user_text))
        # Persist enough of the assistant result to re-render rich cards.
        meta = _slim_meta(result)
        db.add(ChatMessage(
            conversation_id=conv.id, role="assistant",
            text=result.get("reply", ""),
            meta=json.dumps(meta) if meta else None,
        ))
        conv.updated_at = __import__("datetime").datetime.utcnow()
        db.commit()
    except Exception:
        db.rollback()


def claim_session(
    db: Session,
    user: User,
    session_id: str,
    turns: list[dict],
) -> Optional[Conversation]:
    """Attach a pre-login guest transcript to the user's history.

    Idempotent: if a Conversation with this session_id already belongs to the
    user, it is returned without re-inserting the turns (prevents duplicates on
    double-fire). turns: [{role, text, meta?}, ...] — supplied by the frontend
    from its in-memory message list.
    """
    existing = (db.query(Conversation)
                .filter(Conversation.user_id == user.id,
                        Conversation.session_id == session_id)
                .first())
    if existing:
        return existing

    title = next((t["text"] for t in turns if t.get("role") == "user"), "")[:140]
    conv = Conversation(user_id=user.id, session_id=session_id, title=title)
    db.add(conv)
    db.flush()   # get conv.id before adding messages

    for t in turns:
        role = t.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        db.add(ChatMessage(
            conversation_id=conv.id,
            role=role,
            text=t.get("text", ""),
            meta=json.dumps(t["meta"]) if t.get("meta") else None,
        ))
    db.commit()
    return conv


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_or_create_conversation(
    db: Session, user: User, session_id: Optional[str], first_text: str
) -> Conversation:
    if session_id:
        conv = (db.query(Conversation)
                .filter(Conversation.user_id == user.id,
                        Conversation.session_id == session_id)
                .first())
        if conv:
            return conv
    title = first_text[:140]
    conv = Conversation(user_id=user.id, session_id=session_id, title=title)
    db.add(conv)
    db.flush()
    return conv


def _slim_meta(result: dict) -> Optional[dict]:
    """Keep only what the frontend needs to re-render cards on reopen."""
    stores = result.get("stores") or []
    intent = result.get("intent")
    suggestions = result.get("suggestions") or []
    if not stores and not intent:
        return None
    return {
        "intent": intent,
        "suggestions": suggestions,
        # Store ids + names only — avoids a large JSON blob per message.
        "store_ids": [s["id"] for s in stores if s.get("id")],
        "store_names": {s["id"]: s.get("name", "") for s in stores if s.get("id")},
    }

"""Pydantic request/response schemas.

Only the schemas actually used by the routers live here. Endpoints return
hand-built dicts (via common.serializers.store_to_dict), so there are no
response models — these are the request bodies plus the one auth response.
"""
from typing import Annotated, Optional

from pydantic import BaseModel, EmailStr, Field, StringConstraints

# Text that must still say something once surrounding spaces are removed.
NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StoreId = Annotated[str, StringConstraints(max_length=20)]
# Matches Conversation.session_id (String(64)); a frontend UUID is 36 chars.
SessionId = Annotated[str, StringConstraints(min_length=1, max_length=64)]

MAX_LIST_STORES = 200


# ---- auth ----
class RegisterIn(BaseModel):
    name: Annotated[NonBlank, StringConstraints(max_length=60)]
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    token: str
    id: int
    name: str
    email: str
    avatar_url: Optional[str] = None


# ---- auth: google ----
class GoogleAuthIn(BaseModel):
    credential: str = Field(max_length=4096)   # the ID token from Google Identity Services


# ---- stores ----
class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(max_length=2000, default="")


# ---- saved lists ----
class SavedListIn(BaseModel):
    name: Annotated[NonBlank, StringConstraints(max_length=120)]
    store_ids: list[StoreId] = Field(min_length=1, max_length=MAX_LIST_STORES)
    center_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    center_lng: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: Optional[float] = Field(default=None, gt=0, le=50)
    source_label: Optional[str] = Field(default=None, max_length=160)


class SavedListPatch(BaseModel):
    name: Optional[Annotated[NonBlank, StringConstraints(max_length=120)]] = None
    add_ids: list[StoreId] = Field(default_factory=list, max_length=MAX_LIST_STORES)
    remove_ids: list[StoreId] = Field(default_factory=list, max_length=MAX_LIST_STORES)


# ---- chat ----
class Origin(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class ChatAnswer(BaseModel):
    """A tapped answer to the assistant's question (see chat/slots.QUESTIONS)."""
    slot: str = Field(max_length=20)
    value: Optional[str] = Field(None, max_length=40)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: Optional[SessionId] = None
    origin: Optional[Origin] = None
    answer: Optional[ChatAnswer] = None

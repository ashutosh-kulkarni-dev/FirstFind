"""Pydantic request/response schemas.

Only the schemas actually used by the routers live here. Endpoints return
hand-built dicts (via utils.store_to_dict), so there are no response models —
these are the request bodies plus the one auth response.
"""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ---- auth ----
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str
    id: int
    name: str
    email: str
    avatar_url: Optional[str] = None


# ---- auth: google ----
class GoogleAuthIn(BaseModel):
    credential: str   # the ID token from Google Identity Services


# ---- stores ----
class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(max_length=2000, default="")


# ---- saved lists ----
class SavedListIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    store_ids: list[str] = Field(min_length=1)
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    radius_km: Optional[float] = None
    source_label: Optional[str] = Field(default=None, max_length=160)


class SavedListPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    add_ids: list[str] = []
    remove_ids: list[str] = []


# ---- chat ----
class Origin(BaseModel):
    lat: float
    lng: float


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: Optional[str] = None
    origin: Optional[Origin] = None

"""JWT auth utilities and FastAPI dependencies."""
import datetime as dt
import hashlib
import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import JWT_ALGO, JWT_EXPIRE_HOURS, JWT_SECRET
from .database import get_db
from .models import User


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return dk.hex() == dk_hex


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "name": user.name,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _decode(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Required auth."""
    user = get_optional_user(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Optional auth — guest users get None."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    payload = _decode(header[7:])
    if not payload:
        return None
    return db.get(User, int(payload["sub"]))

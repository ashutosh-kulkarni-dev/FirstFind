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


# OWASP 2024 minimum for PBKDF2-SHA256. Older rows were hashed at 120k; they
# verify with the stored iter count and are transparently rehashed on next login
# (see needs_rehash + router usage).
PBKDF2_ITERS = 600_000


def hash_password(password: str, salt: Optional[bytes] = None,
                  iters: int = PBKDF2_ITERS) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    return f"{iters}:{salt.hex()}:{dk.hex()}"


def _parse_stored(stored: str) -> Optional[tuple[int, bytes, str]]:
    """Return (iters, salt, dk_hex) or None if the stored value is malformed.

    Supports both the new 3-part format (`iters:salt:dk`) and the legacy
    2-part format (`salt:dk` — implicitly 120_000 iters) so existing accounts
    keep working. A legacy row is upgraded by the login path.
    """
    parts = stored.split(":")
    try:
        if len(parts) == 3:
            iters = int(parts[0])
            return iters, bytes.fromhex(parts[1]), parts[2]
        if len(parts) == 2:
            return 120_000, bytes.fromhex(parts[0]), parts[1]
    except ValueError:
        return None
    return None


def verify_password(password: str, stored: str) -> bool:
    parsed = _parse_stored(stored)
    if not parsed:
        return False
    iters, salt, dk_hex = parsed
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    return dk.hex() == dk_hex


def needs_rehash(stored: str) -> bool:
    """True if `stored` was hashed with fewer iterations than the current target."""
    parsed = _parse_stored(stored)
    return parsed is None or parsed[0] < PBKDF2_ITERS


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

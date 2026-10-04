from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import (create_token, get_current_user, hash_password,
                    needs_rehash, verify_password)
from ..auth_google import verify_google_token
from ..config import GOOGLE_CLIENT_ID
from ..database import get_db
from ..models import User
from ..schemas import GoogleAuthIn, LoginIn, RegisterIn, TokenOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    """Lowercase + trim so casing never creates duplicate accounts."""
    return email.strip().lower()


def _token_out(user: User) -> TokenOut:
    """Single place that shapes the auth response, for every provider."""
    return TokenOut(token=create_token(user), id=user.id, name=user.name,
                    email=user.email, avatar_url=user.avatar_url)


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "An account with this email already exists")
    user = User(name=body.name, email=email, auth_provider="local",
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_out(user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    user = db.query(User).filter(User.email == email).first()
    # Guide OAuth-only accounts to the right button instead of a generic failure.
    if user and user.auth_provider != "local":
        raise HTTPException(
            400, f"This account uses {user.auth_provider.title()} sign-in. "
                 f"Continue with {user.auth_provider.title()} instead.")
    if not user or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(401, "Invalid email or password")
    # Transparent upgrade: rows hashed at the old iteration count get bumped on
    # the next successful login — no password reset required.
    if needs_rehash(user.password_hash or ""):
        user.password_hash = hash_password(body.password)
        db.commit()
    return _token_out(user)


@router.post("/google", response_model=TokenOut)
def google_auth(body: GoogleAuthIn, db: Session = Depends(get_db)):
    """Verify a Google ID token and return an app JWT.

    Three outcomes:
      - Returning Google user  → look up by google_sub, log in.
      - Existing local account with same email → link it to Google, log in.
      - New user → create with auth_provider="google", no password.
    All three return the same TokenOut so the frontend is provider-agnostic.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google sign-in is not configured on this server")

    identity = verify_google_token(body.credential)
    if identity is None:
        raise HTTPException(401, "Google token invalid or could not be verified")

    # 1. Returning Google user (most common path after first login).
    user = db.query(User).filter(User.google_sub == identity.sub).first()

    if user is None:
        # 2. Existing local account with matching email — link it.
        user = db.query(User).filter(User.email == identity.email).first()
        if user:
            user.google_sub = identity.sub
            user.auth_provider = "google"
            if identity.picture and not user.avatar_url:
                user.avatar_url = identity.picture
            db.commit()
        else:
            # 3. Brand-new user via Google.
            user = User(
                name=identity.name or identity.email.split("@")[0],
                email=identity.email,
                auth_provider="google",
                password_hash=None,
                google_sub=identity.sub,
                avatar_url=identity.picture,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    return _token_out(user)


@router.get("/me", response_model=TokenOut)
def me(user: User = Depends(get_current_user)):
    """Validate the stored token and hydrate the current user on app load.

    Returns a fresh token so a still-valid session silently extends its expiry.
    """
    return _token_out(user)

"""Grant or revoke admin access. There is deliberately no web route for this:
an admin is made by someone with database access.

Run from app/backend:
    python -m app.admin_cli grant someone@example.com
    python -m app.admin_cli revoke someone@example.com
    python -m app.admin_cli list
"""
from __future__ import annotations

import argparse
import sys

from .database import Base, SessionLocal, engine, ensure_schema
from .models import User


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Manage FirstFind admin accounts")
    ap.add_argument("action", choices=["grant", "revoke", "list"])
    ap.add_argument("email", nargs="?")
    args = ap.parse_args(argv)

    Base.metadata.create_all(engine)
    ensure_schema()
    db = SessionLocal()
    try:
        if args.action == "list":
            for u in db.query(User).filter(User.is_admin.is_(True)).order_by(User.email):
                print(u.email)
            return 0
        if not args.email:
            ap.error("email is required for grant / revoke")
        user = db.query(User).filter(User.email == args.email.strip().lower()).first()
        if user is None:
            print(f"No account with email {args.email} — the person must sign up first.")
            return 1
        user.is_admin = args.action == "grant"
        db.commit()
        print(f"{user.email}: admin {'granted' if user.is_admin else 'revoked'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

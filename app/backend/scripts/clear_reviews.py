"""Delete all reviews from the database.

Clears seeded/test reviews used to validate the sentiment model. Store rows,
users, and interactions are left untouched. Store sentiment is derived at read
time, so no cached aggregates need resetting.

Usage (local):
    cd app/backend
    python scripts/clear_reviews.py

Usage (against Supabase prod):
    cd app/backend
    $env:DATABASE_URL = "postgresql+psycopg2://postgres:<pw>@db.<ref>.supabase.co:5432/postgres"
    python scripts/clear_reviews.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Review


def main() -> None:
    db = SessionLocal()
    try:
        before = db.query(Review).count()
        if before == 0:
            print("No reviews to delete.")
            return
        confirm = input(f"Delete {before} reviews? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return
        db.query(Review).delete()
        db.commit()
        after = db.query(Review).count()
        print(f"Deleted {before - after} reviews. {after} remain.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

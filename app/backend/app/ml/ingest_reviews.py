"""External review ingestion — Stage 0 of the ML batch pipeline.

Loads reviews from external sources into the `reviews` table so the existing
sentiment + score pipeline (`pipeline.py`) can process them.

Sources (in priority order):
  1. Local CSV archive  — `data/_archive/googlemaps_reviews.csv`
                          178 real Google Maps reviews, zero API calls.
  2. Google Places API  — weekly live fetch keyed by `Store.google_place_id`;
                          requires GOOGLE_PLACES_API_KEY in env. Enabled by
                          `--google` flag; skipped when no key is set.

Responsible by design:
  - Idempotent: reviews are deduplicated by (store_id, source, external_id).
    Re-running an unchanged source = 0 new rows.
  - Bot attribution: all external reviews are attributed to the system user
    `reviews-bot@thriftfind.local` (seeded by seed.py).
  - Quota-safe: Places calls are throttled, capped by INGEST_MAX_CALLS, and
    cache `google_place_id` per store so Find Place runs only once ever.
  - Non-destructive: never touches existing app-user reviews.

Run:
    python -m app.ml.ingest_reviews               # CSV only
    python -m app.ml.ingest_reviews --run-pipeline  # CSV + score pipeline
    python -m app.ml.ingest_reviews --google --run-pipeline  # + Google Places
"""
from __future__ import annotations

import csv
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..config import (GOOGLE_PLACES_API_KEY, INGEST_MAX_CALLS,
                      INGEST_MIN_INTERVAL_MS)
from ..database import SessionLocal
from ..models import Review, Store, User
from ..seed import BOT_EMAIL

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
REVIEWS_CSV = REPO_ROOT / "data" / "_archive" / "googlemaps_reviews.csv"

# Reference date for relative-date parsing ("2 weeks ago"). The CSV was
# collected around 2024-07-24 (file mtime in the archive).
_CSV_REF_DATE = datetime(2024, 7, 24)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _external_id(store_id: str, reviewer: str, rating: str, date: str) -> str:
    """Stable sha1 hash used as a dedup key."""
    payload = f"{store_id}|{reviewer}|{rating}|{date}"
    return hashlib.sha1(payload.encode()).hexdigest()[:40]


def _parse_relative_date(text: str, ref: datetime = _CSV_REF_DATE) -> datetime:
    """Convert "2 weeks ago", "a month ago", "a year ago" to a datetime."""
    t = text.lower().strip()
    if t in ("a week ago", "1 week ago"):
        return ref - timedelta(weeks=1)
    if t in ("a month ago", "1 month ago"):
        return ref - timedelta(days=30)
    if t in ("a year ago", "1 year ago"):
        return ref - timedelta(days=365)
    m = re.match(r"(\d+)\s*(week|month|year|day)s?\s+ago", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "week":
            return ref - timedelta(weeks=n)
        if unit == "month":
            return ref - timedelta(days=30 * n)
        if unit == "year":
            return ref - timedelta(days=365 * n)
        if unit == "day":
            return ref - timedelta(days=n)
    return ref  # fallback: reference date


def _get_or_create_bot(db) -> User:
    """Return the reviews-bot system user, creating it if absent."""
    bot = db.query(User).filter(User.email == BOT_EMAIL).first()
    if bot is None:
        bot = User(email=BOT_EMAIL, name="Reviews Bot",
                   auth_provider="system", password_hash=None)
        db.add(bot)
        db.flush()
        log.info("Created reviews-bot user (id=%s)", bot.id)
    return bot


def _build_store_index(db) -> dict[str, str]:
    """Return {squashed_name: store_id} for all stores in the DB."""
    return {_squash(s.name): s.id for s in db.query(Store).all()}


# ---------------------------------------------------------------------------
# Source 1: local CSV archive
# ---------------------------------------------------------------------------

def ingest_from_csv(db, bot: User, store_index: dict[str, str]) -> dict:
    """Load googlemaps_reviews.csv into the reviews table, deduped."""
    if not REVIEWS_CSV.exists():
        log.warning("CSV not found: %s — skipping", REVIEWS_CSV)
        return {"source": "csv", "new": 0, "skipped": 0, "unmatched": 0}

    rows = list(csv.DictReader(open(REVIEWS_CSV, encoding="utf-8")))
    new_count = skipped = unmatched = 0

    for row in rows:
        store_id = store_index.get(_squash(row["store_name"]))
        if store_id is None:
            log.debug("No store match for %r", row["store_name"])
            unmatched += 1
            continue

        try:
            rating = int(float(row["rating"]))
        except (ValueError, TypeError):
            continue

        ext_id = _external_id(
            store_id, row.get("reviewer_name", ""),
            row["rating"], row.get("date", ""))

        # Dedup: skip if this external review is already in the DB.
        exists = (db.query(Review.id)
                  .filter(Review.store_id == store_id,
                          Review.source == "google",
                          Review.external_id == ext_id)
                  .first())
        if exists:
            skipped += 1
            continue

        created_at = _parse_relative_date(row.get("date", ""))
        rev = Review(
            store_id=store_id,
            user_id=bot.id,
            rating=max(1, min(5, rating)),
            text=row.get("review_text", ""),
            source="google",
            external_id=ext_id,
            created_at=created_at,
        )
        db.add(rev)
        new_count += 1

    db.flush()
    result = {"source": "csv", "new": new_count,
              "skipped": skipped, "unmatched": unmatched}
    log.info("CSV ingest: %s", result)
    return result


# ---------------------------------------------------------------------------
# Source 2: Google Places API (weekly live refresh)
# ---------------------------------------------------------------------------

def _places_get(session, url: str, params: dict, call_counter: list) -> dict | None:
    """Make one Places API call; return None on error or budget exceeded."""
    if call_counter[0] >= INGEST_MAX_CALLS:
        log.warning("Places API call cap (%d) reached — aborting further calls",
                    INGEST_MAX_CALLS)
        return None
    call_counter[0] += 1
    try:
        resp = session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("Places API error: %s", e)
        return None


def _resolve_place_id(session, store: Store, call_counter: list) -> str | None:
    """Find Place From Text → cache google_place_id on the Store row."""
    if store.google_place_id:
        return store.google_place_id
    if not store.lat or not store.lng:
        return None
    data = _places_get(session,
        "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
        {
            "input": f"{store.name} {store.locality_raw or store.area} {store.city}",
            "inputtype": "textquery",
            "locationbias": f"circle:200@{store.lat},{store.lng}",
            "fields": "place_id",
            "key": GOOGLE_PLACES_API_KEY,
        }, call_counter)
    candidates = (data or {}).get("candidates", [])
    if not candidates:
        return None
    place_id = candidates[0].get("place_id")
    if place_id:
        store.google_place_id = place_id
    return place_id


def ingest_from_google(db, bot: User, limit: int | None = None) -> dict:
    """Fetch current reviews for each store from the Google Places API."""
    if not GOOGLE_PLACES_API_KEY:
        log.info("No GOOGLE_PLACES_API_KEY set — skipping Google Places ingest")
        return {"source": "google_api", "new": 0, "skipped": 0, "no_place_id": 0}

    try:
        import httpx
        session = httpx.Client(timeout=10)
    except ImportError:
        log.error("httpx not available for Google Places calls")
        return {"source": "google_api", "new": 0, "skipped": 0, "no_place_id": 0}

    stores = db.query(Store).all()
    if limit:
        stores = stores[:limit]

    call_counter = [0]
    new_count = skipped = no_place = 0
    interval_s = INGEST_MIN_INTERVAL_MS / 1000

    for store in stores:
        if call_counter[0] >= INGEST_MAX_CALLS:
            break
        place_id = _resolve_place_id(session, store, call_counter)
        if not place_id:
            no_place += 1
            continue

        time.sleep(interval_s)
        data = _places_get(session,
            "https://maps.googleapis.com/maps/api/place/details/json",
            {
                "place_id": place_id,
                "fields": "reviews,rating,user_ratings_total",
                "key": GOOGLE_PLACES_API_KEY,
            }, call_counter)

        reviews_raw = (data or {}).get("result", {}).get("reviews", [])
        for r in reviews_raw:
            rating = max(1, min(5, int(r.get("rating", 3))))
            reviewer = r.get("author_name", "")
            date_str = r.get("relative_time_description", "")
            ext_id = _external_id(store.id, reviewer, str(rating), date_str)

            exists = (db.query(Review.id)
                      .filter(Review.store_id == store.id,
                              Review.source == "google",
                              Review.external_id == ext_id)
                      .first())
            if exists:
                skipped += 1
                continue

            rev = Review(
                store_id=store.id,
                user_id=bot.id,
                rating=rating,
                text=r.get("text", ""),
                source="google",
                external_id=ext_id,
                created_at=datetime.utcnow(),
            )
            db.add(rev)
            new_count += 1

        time.sleep(interval_s)

    db.flush()
    result = {"source": "google_api", "new": new_count,
              "skipped": skipped, "no_place_id": no_place,
              "api_calls": call_counter[0]}
    log.info("Google Places ingest: %s", result)
    return result


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def ingest_all(db=None, use_google: bool = False,
               google_limit: int | None = None) -> dict:
    """Run all enabled ingestion sources. Returns combined summary."""
    own = db is None
    db = db or SessionLocal()
    try:
        bot = _get_or_create_bot(db)
        store_index = _build_store_index(db)

        results = []
        results.append(ingest_from_csv(db, bot, store_index))
        if use_google:
            results.append(ingest_from_google(db, bot, limit=google_limit))

        db.commit()
        total_new = sum(r.get("new", 0) for r in results)
        log.info("Ingest complete — %d new reviews across %d sources",
                 total_new, len(results))
        return {"sources": results, "total_new": total_new}
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Ingest external reviews into the DB")
    ap.add_argument("--google", action="store_true",
                    help="also fetch from Google Places API")
    ap.add_argument("--google-limit", type=int, default=None,
                    help="limit Google Places to N stores (testing)")
    ap.add_argument("--run-pipeline", action="store_true",
                    help="run the full ML pipeline after ingestion")
    args = ap.parse_args()

    summary = ingest_all(use_google=args.google, google_limit=args.google_limit)
    for r in summary["sources"]:
        print(f"  [{r['source']}] new={r.get('new',0)}  "
              f"skipped={r.get('skipped',0)}")
    print(f"Total new reviews: {summary['total_new']}")

    if args.run_pipeline:
        from .pipeline import run_pipeline
        print("Running ML pipeline...")
        result = run_pipeline()
        print(f"Pipeline: {result['reviews_scored']} scored, "
              f"{result['stores_rescored']} stores rescored, "
              f"{result['zones']} zones")

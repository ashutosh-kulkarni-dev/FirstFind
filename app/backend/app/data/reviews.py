"""External review ingestion — Stage 0 of the ML batch pipeline.

Loads reviews from external sources into the `reviews` table so the existing
sentiment + score pipeline (`jobs/pipeline.py`) can process them.

Sources (in priority order):
  1. Local CSV          — `data/import/reviews.csv` (keyed by store id).
                          Zero API calls.
  2. Google Places API (New) — weekly live fetch keyed by `Store.google_place_id`;
                          requires GOOGLE_PLACES_API_KEY in env. Enabled by
                          `--google` flag; skipped when no key is set.

Responsible by design:
  - Idempotent: reviews are deduplicated by (store_id, source, external_id),
    where external_id hashes store + author + review text. It deliberately
    ignores the date: Google only gives relative dates ("2 weeks ago") that
    change every week, which would re-insert the same review on each run.
  - Bot attribution: all external reviews are attributed to the system user
    `reviews-bot@thriftfind.local` (created on first use).
  - Quota-safe: Places calls are throttled, capped by INGEST_MAX_CALLS, and
    cache `google_place_id` per store so Find Place runs only once ever.
  - Non-destructive: never touches existing app-user reviews.

Run:
    python -m app.data.reviews               # CSV only
    python -m app.data.reviews --run-pipeline  # CSV + score pipeline
    python -m app.data.reviews --google --run-pipeline  # + Google Places
"""
from __future__ import annotations

import csv
import hashlib
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from ..common.geo import utcnow
from ..common.aliases import alias_for
from ..config import BOT_EMAIL, GOOGLE_PLACES_API_KEY, INGEST_MAX_DETAILS
from ..database import SessionLocal
from ..models import Review, Store, User


log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
REVIEWS_CSV = REPO_ROOT / "data" / "import" / "reviews.csv"

# Reference date for relative-date parsing ("2 weeks ago") — when the CSV was
# collected. Override with --ref-date YYYY-MM-DD when importing a newer scrape.
_CSV_REF_DATE = datetime(2026, 11, 3)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _review_key(store_id: str, author: str, text: str) -> str:
    """Stable dedup key: store + author + normalised review text (no date)."""
    norm = re.sub(r"\s+", " ", (text or "").strip().lower())[:300]
    payload = f"{store_id}|{(author or '').strip().lower()}|{norm}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:40]


_REL_DATE_RE = re.compile(r"(an?|\d+)\s*(minute|hour|day|week|month|year)s?\s+ago")
_REL_UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def _parse_relative_date(text: str, ref: datetime = _CSV_REF_DATE) -> datetime:
    """Convert "2 weeks ago", "a month ago", "Edited a year ago" to a datetime.
    An absolute ISO date ("2026-10-21...") is used as-is."""
    iso = re.match(r"\d{4}-\d{2}-\d{2}", (text or "").strip())
    if iso:
        return datetime.strptime(iso.group(0), "%Y-%m-%d")
    m = _REL_DATE_RE.search((text or "").lower())
    if not m:
        return ref  # fallback: reference date
    n = 1 if m.group(1) in ("a", "an") else int(m.group(1))
    return ref - timedelta(days=n * _REL_UNIT_DAYS[m.group(2)])


def _existing_keys(db) -> set[tuple[str, str]]:
    """(store_id, external_id) for every external review already stored."""
    return {(sid, ext) for sid, ext in
            db.query(Review.store_id, Review.external_id)
            .filter(Review.source == "google", Review.external_id.isnot(None))}


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

def ingest_from_csv(db, bot: User, store_index: dict[str, str],
                    seen: set[tuple[str, str]] | None = None,
                    csv_path: Path | None = None,
                    ref_date: datetime = _CSV_REF_DATE) -> dict:
    """Load a reviews CSV into the reviews table, deduped.

    Accepts both layouts: the current one (`store_id, author, ...`) and the
    legacy archive (`store_name, reviewer_name, ...`, matched by name).
    `seen` carries the dedup keys across sources within one run — needed
    because rows added in this session are not yet visible to a DB query.
    """
    if csv_path is None:
        csv_path = REVIEWS_CSV
    if not csv_path.exists():
        log.warning("CSV not found: %s — skipping", csv_path)
        return {"source": "csv", "new": 0, "skipped": 0, "unmatched": 0}
    if seen is None:
        seen = _existing_keys(db)

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    valid_ids = set(store_index.values())
    new_count = skipped = unmatched = bad = named = 0
    # The real reviewer's name is never kept: every imported review is stored
    # under a random alias. Rows saved earlier (no name, or a real one) are
    # switched to their alias here.
    for old in db.query(Review).filter(Review.source == "google",
                                       Review.external_id.isnot(None)).all():
        alias = alias_for(old.store_id, old.external_id)
        if old.author_name != alias:
            old.author_name = alias
            named += 1

    for row in rows:
        store_id = (row.get("store_id") or "").strip()
        if store_id not in valid_ids:
            store_id = store_index.get(_squash(row.get("store_name") or ""))
        if store_id is None:
            log.debug("No store match for %r", row.get("store_name"))
            unmatched += 1
            continue

        try:
            rating = int(float(row["rating"]))
        except (KeyError, ValueError, TypeError):
            bad += 1
            continue

        author = row.get("author") or row.get("reviewer_name") or ""
        text = row.get("review_text") or ""
        key = (store_id, _review_key(store_id, author, text))
        if key in seen:
            skipped += 1
            continue
        seen.add(key)

        db.add(Review(
            store_id=store_id,
            user_id=bot.id,
            author_name=alias_for(store_id, key[1]),
            rating=max(1, min(5, rating)),
            text=text,
            source="google",
            external_id=key[1],
            created_at=_parse_relative_date(row.get("date", ""), ref_date),
        ))
        new_count += 1

    db.flush()
    result = {"source": "csv", "file": csv_path.name, "new": new_count,
              "skipped": skipped, "unmatched": unmatched, "bad_rows": bad,
              "names_filled": named}
    log.info("CSV ingest: %s", result)
    return result


# ---------------------------------------------------------------------------
# Source 2: Google Places API (New) — weekly live refresh
# ---------------------------------------------------------------------------

def _resolve_place_id(client, store: Store) -> str | None:
    """Text Search (ids only) -> cache google_place_id on the Store row."""
    if store.google_place_id:
        return store.google_place_id
    places = client.search_text(
        f"{store.name} {store.locality_raw or store.area} {store.city or 'Bengaluru'}",
        store.lat, store.lng, fields="places.id", radius_m=200, page_size=1)
    if not places:
        return None
    store.google_place_id = places[0].get("id")
    return store.google_place_id


def ingest_from_google(db, bot: User, limit: int | None = None,
                       seen: set[tuple[str, str]] | None = None,
                       client=None) -> dict:
    """Fetch current reviews for each store from the Google Places API (New)."""
    from ..google.places import PlacesBudgetExceeded, PlacesClient, parse_reviews

    if client is None:
        if not GOOGLE_PLACES_API_KEY:
            log.info("No GOOGLE_PLACES_API_KEY set — skipping Google Places ingest")
            return {"source": "google_api", "new": 0, "skipped": 0, "no_place_id": 0}
        client = PlacesClient()
    if seen is None:
        seen = _existing_keys(db)

    # Rotate: never-fetched stores first, then the ones fetched longest ago.
    # The per-run call cap (INGEST_MAX_CALLS) covers only part of the catalogue,
    # so a fixed order would refresh the same stores every week and never
    # reach the rest. Hidden stores (no pin / inactive) are skipped.
    stores = [s for s in db.query(Store).all()
              if s.lat is not None and s.lng is not None and s.is_active is not False]
    stores.sort(key=lambda s: (s.reviews_fetched_at is not None,
                               s.reviews_fetched_at or datetime.min, s.id))
    if limit:
        stores = stores[:limit]

    new_count = skipped = no_place = errors = visited = 0
    reviewed_places = 0          # visited stores Google says have reviews
    reviews_unavailable = False
    for store in stores:
        # Some keys (e.g. the Maps demo key) return ratings but never review
        # text. Detect that early and stop, rather than spend the day's quota.
        if reviewed_places >= 5 and new_count + skipped == 0:
            log.warning("This Google key returns no review text (5 reviewed stores, 0 reviews) "
                        "— stopping the review fetch for this run")
            reviews_unavailable = True
            break
        if visited >= INGEST_MAX_DETAILS:
            log.info("Details cap (%d) reached — the rest wait for the next run",
                     INGEST_MAX_DETAILS)
            break
        try:
            place_id = _resolve_place_id(client, store)
            if not place_id:
                no_place += 1
                store.reviews_fetched_at = utcnow()   # don't retry every week
                continue
            place = client.details(place_id, "rating,userRatingCount,businessStatus,reviews")
        except PlacesBudgetExceeded:
            log.info("Places call cap reached after %d stores — the rest wait for the next run",
                     visited)
            break
        except (httpx.HTTPError, ValueError) as e:
            log.warning("Places API error for %s: %s", store.id, e)
            errors += 1
            if errors >= 5 and visited == 0:
                log.error("Places API failing on every call — aborting the Google ingest")
                break
            continue

        visited += 1
        store.reviews_fetched_at = utcnow()
        # Keep the Google aggregates fresh while we are here (same API call).
        if place.get("rating") is not None:
            store.google_rating = float(place["rating"])
        if place.get("userRatingCount") is not None:
            store.google_review_count = int(place["userRatingCount"])
        if (place.get("userRatingCount") or 0) > 0:
            reviewed_places += 1
        if place.get("businessStatus") == "CLOSED_PERMANENTLY":
            store.is_active = False

        for r in parse_reviews(place):
            key = (store.id, _review_key(store.id, r["author"], r["text"]))
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            db.add(Review(
                store_id=store.id, user_id=bot.id, rating=r["rating"],
                author_name=alias_for(store.id, key[1]),
                text=r["text"], source="google", external_id=key[1],
                created_at=r["created_at"] or utcnow(),
            ))
            new_count += 1

    db.flush()
    result = {"source": "google_api", "new": new_count, "skipped": skipped,
              "no_place_id": no_place, "stores_visited": visited,
              "errors": errors, "api_calls": client.calls,
              "reviews_unavailable": reviews_unavailable}
    log.info("Google Places ingest: %s", result)
    return result


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def ingest_all(db=None, use_google: bool = False,
               google_limit: int | None = None,
               csv_path: Path | None = None,
               ref_date: datetime = _CSV_REF_DATE,
               google_client=None) -> dict:
    """Run all enabled ingestion sources. Returns combined summary.

    `google_client` lets the daily job pass a client that has already spent
    part of the day's call budget on candidate verification."""
    own = db is None
    db = db or SessionLocal()
    try:
        bot = _get_or_create_bot(db)
        store_index = _build_store_index(db)

        seen = _existing_keys(db)
        results = []
        results.append(ingest_from_csv(db, bot, store_index, seen,
                                       csv_path=csv_path, ref_date=ref_date))
        if use_google:
            results.append(ingest_from_google(db, bot, limit=google_limit, seen=seen,
                                              client=google_client))

        db.commit()
        total_new = sum(r.get("new", 0) for r in results)
        log.info("Ingest complete — %d new reviews across %d sources",
                 total_new, len(results))
        return {"sources": results, "total_new": total_new,
                "total_in_db": db.query(Review).count()}
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
    ap.add_argument("--csv", type=Path, default=None,
                    help="reviews CSV (default: data/import/reviews.csv)")
    ap.add_argument("--ref-date", type=lambda v: datetime.strptime(v, "%Y-%m-%d"),
                    default=_CSV_REF_DATE,
                    help="date the CSV was collected, for '2 weeks ago' dates")
    args = ap.parse_args()

    summary = ingest_all(use_google=args.google, google_limit=args.google_limit,
                         csv_path=args.csv, ref_date=args.ref_date)
    for r in summary["sources"]:
        print(f"  [{r['source']}] new={r.get('new',0)}  "
              f"skipped={r.get('skipped',0)}  unmatched={r.get('unmatched',0)}")
    print(f"Total new reviews: {summary['total_new']}  "
          f"(reviews in DB: {summary['total_in_db']})")
    if summary["total_in_db"] == 0:
        # Fail the scheduled job loudly rather than "succeed" with an empty app.
        raise SystemExit("ERROR: no reviews in the database after ingest — "
                         "check the CSV path and that stores are imported.")

    if args.run_pipeline:
        from ..jobs.pipeline import run_pipeline
        print("Running ML pipeline...")
        result = run_pipeline()
        print(f"Pipeline: {result['reviews_scored']} scored, "
              f"{result['stores_rescored']} stores rescored, "
              f"{result['zones']} zones")

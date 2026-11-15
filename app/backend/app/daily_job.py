"""The one scheduled job. Run daily by .github/workflows/reviews-refresh.yml.

Steps, in order — each is idempotent, so a failed or repeated run is harmless:

  1. VERIFY   up to GOOGLE_DAILY_BUDGET unchecked candidate stores with Google
              (hand-added candidates first), until the backlog is empty.
  2. PROMOTE  the verified ones into data/import/stores.csv (+ their reviews,
              when the key returns any, into data/import/reviews.csv).
  3. IMPORT   stores.csv into the database (fill-only upsert, never deletes).
  4. REVIEWS  load reviews.csv, then spend whatever is LEFT of today's Google
              budget fetching reviews / fresh ratings for the stores checked
              longest ago.
  5. PIPELINE sentiment for new reviews, AI scores, zones, recommendations,
              store descriptions.

Google budget: steps 1 and 4 share GOOGLE_DAILY_BUDGET calls (default 90, for
a key limited to 100/day). Verification has priority; once the candidate
backlog is cleared the whole budget goes to step 4. Without
GOOGLE_PLACES_API_KEY steps 1, 2 and the Google half of 4 are skipped.

The CSV files it updates must be committed back to the repo by the workflow —
they are the record of which candidates have been checked.

Run from app/backend:
    python -m app.daily_job
    python -m app.daily_job --no-google      # CSV import + pipeline only
"""
from __future__ import annotations

import argparse
import logging
import os

from . import verify_candidates as V
from .config import GOOGLE_PLACES_API_KEY
from .database import Base, SessionLocal, engine, ensure_schema

log = logging.getLogger(__name__)

GOOGLE_DAILY_BUDGET = int(os.environ.get("GOOGLE_DAILY_BUDGET", "90"))


def verify_and_promote(client, budget: int) -> dict:
    """Steps 1 + 2. Returns a summary; saves progress after every candidate."""
    cands, fields = V.load_candidates()
    sidecar = V.load_reviews_sidecar()
    todo = V.unchecked(cands)
    tally = {}
    if todo and budget > 0:
        try:
            tally = dict(V.verify(client, todo, budget, reviews=sidecar,
                                  on_progress=lambda: V.save_state(cands, fields, sidecar)))
        finally:
            V.save_state(cands, fields, sidecar)
    new_stores, new_reviews = V.promote_files(cands, fields, sidecar, write=True)
    return {"checked": tally, "stores_added": len(new_stores),
            "reviews_added": len(new_reviews),
            "backlog": len(V.unchecked(cands))}


def run(use_google: bool = True, budget: int = GOOGLE_DAILY_BUDGET) -> dict:
    from .importer import import_stores
    from .ml.ingest_reviews import ingest_all
    from .ml.pipeline import run_pipeline

    Base.metadata.create_all(engine)
    ensure_schema()

    summary: dict = {}
    client = None
    if use_google and GOOGLE_PLACES_API_KEY:
        from .ml.google_places import PlacesClient
        client = PlacesClient(max_calls=budget)
        summary["candidates"] = verify_and_promote(client, budget)
    else:
        log.info("Google steps skipped (%s)",
                 "--no-google" if not use_google else "no GOOGLE_PLACES_API_KEY")

    db = SessionLocal()
    try:
        report = import_stores(db)
        db.commit()
        summary["stores"] = {k: report[k] for k in ("created", "updated", "total_in_db")}
        summary["stores"]["hidden_no_pin"] = len(report["no_coords"])
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    left = (client.max_calls - client.calls) if client else 0
    summary["reviews"] = ingest_all(use_google=left > 0, google_client=client)
    summary["google_calls_used"] = client.calls if client else 0
    summary["pipeline"] = _with_retries(run_pipeline)
    return summary


def _with_retries(fn, attempts: int = 3):
    """Re-run an idempotent step if the database reports a deadlock or lock
    timeout — the live web app writes to the same tables while this job runs."""
    import time

    from sqlalchemy.exc import OperationalError
    for n in range(1, attempts + 1):
        try:
            return fn()
        except OperationalError as e:
            if n == attempts:
                raise
            log.warning("Database contention (%s) — retry %d/%d in 20s",
                        str(e).splitlines()[0][:120], n, attempts - 1)
            time.sleep(20)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="FirstFind daily data job")
    ap.add_argument("--no-google", action="store_true", help="skip every Google call")
    ap.add_argument("--budget", type=int, default=GOOGLE_DAILY_BUDGET,
                    help="max Google calls this run")
    args = ap.parse_args()

    summary = run(use_google=not args.no_google, budget=args.budget)
    print("\n=== Daily job summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    if summary["reviews"]["total_in_db"] == 0:
        # Fail loudly rather than "succeed" with an empty app.
        raise SystemExit("ERROR: no reviews in the database after the run — "
                         "check data/import/reviews.csv and that stores were imported.")


if __name__ == "__main__":
    main()

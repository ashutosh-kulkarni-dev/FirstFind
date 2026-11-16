"""The one scheduled job. Run daily by .github/workflows/reviews-refresh.yml.

Every day:

  1. VERIFY   the stores we list against Google (app/store_check.py): about
              GOOGLE_DAILY_BUDGET stores a day, the ones checked longest ago
              first. Permanently closed stores are hidden; Google ratings are
              refreshed. Adds no stores. Skipped without GOOGLE_PLACES_API_KEY.
  2. SCORE    sentiment for new reviews, AI scores, zones, recommendations,
              store descriptions.

Only on a manual run (workflow inputs / environment variables):

  IMPORT_CSV=true     load data/import/stores.csv, hidden_stores.csv and
                      reviews.csv into the database first (fill-only upsert).
  PRUNE_STORES=true   also delete stores that are not in stores.csv.
  ADD_VERIFIED_CANDIDATES=true
                      verify OpenStreetMap candidates and ADD the matches as
                      new stores. Off: the store list is the owner's CSV only.

Run from app/backend:
    python -m app.daily_job
    python -m app.daily_job --no-google      # scoring only
    python -m app.daily_job --import-csv     # after editing the CSV files
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
_ON = ("1", "true", "yes")
IMPORT_CSV = os.environ.get("IMPORT_CSV", "").lower() in _ON
PRUNE_STORES = os.environ.get("PRUNE_STORES", "").lower() in _ON
ADD_VERIFIED_CANDIDATES = os.environ.get("ADD_VERIFIED_CANDIDATES", "").lower() in _ON


def verify_and_promote(client, budget: int) -> dict:
    """Optional: check candidate stores and add the matches to stores.csv."""
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


def run(use_google: bool = True, budget: int = GOOGLE_DAILY_BUDGET,
        add_candidates: bool | None = None, prune: bool | None = None,
        import_csv: bool | None = None) -> dict:
    from .importer import import_stores, prune_stores
    from .ml.ingest_reviews import ingest_all
    from .ml.pipeline import run_pipeline
    from .models import Review
    from .store_check import verify_stores
    add_candidates = ADD_VERIFIED_CANDIDATES if add_candidates is None else add_candidates
    prune = PRUNE_STORES if prune is None else prune
    import_csv = IMPORT_CSV if import_csv is None else import_csv
    import_csv = import_csv or prune or add_candidates   # both need the CSV loaded

    Base.metadata.create_all(engine)
    ensure_schema()

    summary: dict = {}
    client = None
    if use_google and GOOGLE_PLACES_API_KEY:
        from .ml.google_places import PlacesClient
        client = PlacesClient(max_calls=budget)
        if add_candidates:
            summary["candidates"] = verify_and_promote(client, budget)
    else:
        log.warning("Store verification skipped (%s)",
                    "--no-google" if not use_google else "no GOOGLE_PLACES_API_KEY")

    db = SessionLocal()
    try:
        if import_csv:
            report = import_stores(db)
            if prune:
                summary["pruned"] = prune_stores(db)
                report["total_in_db"] -= summary["pruned"]["stores_removed"]
            db.commit()
            summary["stores"] = {k: report[k] for k in ("created", "updated", "total_in_db")}
            summary["stores"]["hidden_no_pin"] = len(report["no_coords"])
            summary["reviews_csv"] = ingest_all(db)["sources"][0]
        if client is not None and client.calls < client.max_calls:
            summary["verification"] = verify_stores(db, client)
        summary["reviews_in_db"] = db.query(Review).count()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

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
    ap = argparse.ArgumentParser(description="FirstFind daily store verification job")
    ap.add_argument("--no-google", action="store_true", help="skip every Google call")
    ap.add_argument("--budget", type=int, default=GOOGLE_DAILY_BUDGET,
                    help="max Google calls this run")
    ap.add_argument("--import-csv", action="store_true",
                    help="load data/import/*.csv into the database first")
    args = ap.parse_args()

    summary = run(use_google=not args.no_google, budget=args.budget,
                  import_csv=True if args.import_csv else None)
    print("\n=== Daily job summary ===")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

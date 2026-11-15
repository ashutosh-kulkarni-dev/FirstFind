"""Regressions from the first production run of the daily job.

  * boot must not ALTER tables that are already up to date (deadlocked the job)
  * reviews keep the real reviewer's name, and old rows get it backfilled
  * unscored reviews are not counted as neutral
  * a 402 from HuggingFace switches the hosted engine off instead of retrying
  * VADER-scored reviews are re-scored once a real model engine is available
"""
import csv

import httpx
import pytest
from sqlalchemy import event

from app import importer
from app.database import SessionLocal, engine, ensure_schema
from app.ml import ingest_reviews, pipeline
from app.ml import sentiment as S
from app.models import Review, Store
from app.utils import sentiment_summary


def test_ensure_schema_issues_no_alter_when_up_to_date():
    ensure_schema()                      # bring the test DB up to date first
    statements = []

    def record(conn, cursor, statement, *a):
        statements.append(statement)
    event.listen(engine, "before_cursor_execute", record)
    try:
        ensure_schema()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert not [s for s in statements if "ALTER" in s.upper()]


@pytest.fixture()
def db():
    ensure_schema()
    s = SessionLocal()
    yield s
    s.rollback()
    s.query(Review).filter(Review.store_id.like("fx-%")).delete(synchronize_session=False)
    s.query(Store).filter(Store.id.like("fx-%")).delete(synchronize_session=False)
    s.commit()
    s.close()


RF = ["review_id", "store_id", "store_name", "author", "rating", "review_text", "date", "source"]


def _reviews_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RF)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RF})


def test_reviewer_names_are_stored_served_and_backfilled(db, tmp_path, client):
    db.add(Store(id="fx-1", name="Fix Shop", area="Indiranagar", lat=12.97, lng=77.64))
    db.commit()
    rp = tmp_path / "reviews.csv"
    _reviews_csv(rp, [{"store_id": "fx-1", "author": "Asha Rao", "rating": "5",
                       "review_text": "Great finds", "date": "a week ago"}])
    ingest_reviews.ingest_all(db, csv_path=rp)
    r = db.query(Review).filter(Review.store_id == "fx-1").one()
    assert r.author_name == "Asha Rao"

    shown = client.get("/api/stores/fx-1").json()["reviews"][0]
    assert shown["user_name"] == "Asha Rao" and shown["source"] == "google"

    # A row ingested before names were kept gets its name on the next run.
    r.author_name = None
    db.commit()
    out = ingest_reviews.ingest_all(db, csv_path=rp)["sources"][0]
    assert (out["new"], out["names_filled"]) == (0, 1)
    db.expire_all()
    assert db.query(Review).filter(Review.store_id == "fx-1").one().author_name == "Asha Rao"


def test_sentiment_summary_separates_unscored():
    class R:
        def __init__(self, s): self.sentiment = s
    out = sentiment_summary([R("positive"), R("positive"), R("negative"), R("neutral"), R(None), R(None)])
    assert out == {"positive": 2, "neutral": 1, "negative": 1, "unscored": 2, "total": 6}


def _http_error(status):
    req = httpx.Request("POST", "https://router.huggingface.co/x")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(status, request=req))


def test_402_switches_hosted_models_off(monkeypatch):
    monkeypatch.setattr(S, "hf_token", "t")
    monkeypatch.setattr(S, "SENTIMENT_LOCAL", False)
    monkeypatch.setattr(S, "_hf_disabled", False)
    monkeypatch.setattr(S, "HF_SENTIMENT_MODELS", ["a", "b"])
    calls = []

    def paywalled(model, text):
        calls.append(model)
        raise _http_error(402)
    monkeypatch.setattr(S, "_hf_probs", paywalled)

    assert S.best_engine() == "hf"
    label, _, engine = S.analyze_detail("great store")
    assert (label, engine) == ("positive", "vader")
    assert calls == ["a"]                    # stopped after the first 402, did not try "b"
    assert S.best_engine() == "vader"
    S.analyze_detail("great store")
    assert calls == ["a"]                    # and never calls the API again this run


def test_local_engine_is_preferred_and_recorded(monkeypatch):
    monkeypatch.setattr(S, "local_available", lambda: True)
    monkeypatch.setattr(S, "LOCAL_SENTIMENT_MODELS", ["m"])
    monkeypatch.setattr(S, "_local_probs", lambda m, t: {"negative": .8, "neutral": .1, "positive": .1})
    assert S.best_engine() == "local"
    assert S.analyze_detail("Ekdum bakwaas") == ("negative", -0.7, "local")


def test_pipeline_rescores_vader_reviews_when_models_are_available(db, monkeypatch):
    user_id = ingest_reviews._get_or_create_bot(db).id
    db.add(Store(id="fx-2", name="Rescore Shop", area="Indiranagar", lat=12.97, lng=77.64))
    db.add_all([
        Review(store_id="fx-2", user_id=user_id, rating=1, text="Ekdum bakwaas",
               sentiment="neutral", sentiment_score=0.0, sentiment_engine="vader"),
        Review(store_id="fx-2", user_id=user_id, rating=5, text="Lovely",
               sentiment="positive", sentiment_score=0.9, sentiment_engine="local"),
        Review(store_id="fx-2", user_id=user_id, rating=4, text="New one"),
    ])
    db.commit()
    seen = []

    def fake(text, rating=None):
        seen.append(text)
        return "negative", -0.8, "local"
    monkeypatch.setattr(S, "analyze_detail", fake)

    # No model engine: only the brand-new review is scored; VADER rows are left.
    monkeypatch.setattr(S, "best_engine", lambda: "vader")
    others = db.query(Review).filter(Review.sentiment.is_(None), ~Review.store_id.like("fx-%")).count()
    assert pipeline.score_pending_sentiment(db) == 1 + others
    assert "Ekdum bakwaas" not in seen and "New one" in seen

    # Models available: the VADER row is redone; the "local" row is not.
    seen.clear()
    monkeypatch.setattr(S, "best_engine", lambda: "local")
    pipeline.score_pending_sentiment(db)
    assert "Ekdum bakwaas" in seen and "Lovely" not in seen
    db.expire_all()
    redo = db.query(Review).filter(Review.store_id == "fx-2", Review.text == "Ekdum bakwaas").one()
    assert (redo.sentiment, redo.sentiment_engine) == ("negative", "local")


def test_importer_path_is_resolved_at_call_time(monkeypatch, tmp_path, db):
    p = tmp_path / "stores.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "locality_raw", "lat", "lng"])
        w.writeheader()
        w.writerow({"id": "fx-3", "name": "Path Shop", "locality_raw": "Indiranagar",
                    "lat": "12.97", "lng": "77.64"})
    monkeypatch.setattr(importer, "STORES_CSV", p)
    assert importer.import_stores(db)["rows"] == 1

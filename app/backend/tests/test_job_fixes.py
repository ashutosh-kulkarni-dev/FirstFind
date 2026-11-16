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
    alias = r.author_name
    assert alias and alias != "Asha Rao"       # the real name is never stored

    shown = client.get("/api/stores/fx-1").json()["reviews"][0]
    # The page shows a random alias: never the real name, never the bot, and
    # the same alias every time.
    assert shown["source"] == "google"
    assert shown["user_name"] == alias
    assert client.get("/api/stores/fx-1").json()["reviews"][0]["user_name"] == shown["user_name"]

    # A row saved earlier under the real name is switched to its alias.
    r.author_name = "Asha Rao"
    db.commit()
    out = ingest_reviews.ingest_all(db, csv_path=rp)["sources"][0]
    assert (out["new"], out["names_filled"]) == (0, 1)
    db.expire_all()
    assert db.query(Review).filter(Review.store_id == "fx-1").one().author_name == alias


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


def test_hidden_stores_file_switches_a_store_off(tmp_path, db):
    p = tmp_path / "stores.csv"
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "locality_raw", "lat", "lng"])
        w.writeheader()
        for i in ("fx-8", "fx-9"):
            w.writerow({"id": i, "name": "Shop " + i, "locality_raw": "Indiranagar",
                        "lat": "12.97", "lng": "77.64"})
    importer.import_stores(db, p)
    db.commit()
    assert db.get(Store, "fx-9").is_active is not False

    (tmp_path / "hidden_stores.csv").write_text(
        "id,name,reason\nfx-9,Shop fx-9,not a clothing store\n", encoding="utf-8")
    importer.import_stores(db, p)
    db.commit()
    db.expire_all()
    assert db.get(Store, "fx-9").is_active is False
    assert db.get(Store, "fx-8").is_active is not False


def test_prune_removes_only_stores_missing_from_the_csv(tmp_path, db):
    import pytest as _pt
    p = tmp_path / "stores.csv"
    real = [sid for (sid,) in db.query(Store.id) if not sid.startswith("fx-")]

    def write(ids):
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "name", "locality_raw", "lat", "lng"])
            w.writeheader()
            for i in ids:
                w.writerow({"id": i, "name": "Shop " + i, "locality_raw": "Indiranagar",
                            "lat": "12.97", "lng": "77.64"})
    extra = ["fx-p%d" % n for n in range(6)]
    write(real + extra)
    importer.import_stores(db, p)
    bot = ingest_reviews._get_or_create_bot(db)
    db.add(Review(store_id="fx-p5", user_id=bot.id, rating=5, text="bye"))
    db.commit()

    write(real + extra[:5])                       # fx-p5 is no longer in the CSV
    out = importer.prune_stores(db, p)
    db.commit()
    assert out["ids"] == ["fx-p5"] and out["reviews_removed"] == 1
    assert db.get(Store, "fx-p5") is None and db.get(Store, "fx-p4") is not None
    assert db.query(Review).filter(Review.store_id == "fx-p5").count() == 0

    write(extra[:1])                              # a broken CSV must not wipe the DB
    with _pt.raises(RuntimeError):
        importer.prune_stores(db, p)
    db.rollback()

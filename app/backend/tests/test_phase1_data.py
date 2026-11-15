"""Store importer, review ingest dedup, AI-score formula, sentiment routing.

All offline: SQLite from conftest, no HF / Groq keys.
"""
import csv

import pytest

from app import importer
from app.database import SessionLocal, ensure_schema
from app.ml import ingest_reviews
from app.ml import sentiment as S
from app.models import Review, Store
from app.utils import has_coords


# ---------------------------------------------------------------- cleaning --

@pytest.mark.parametrize("raw,want", [
    ("10:00 AM", "10:00"), ("9:30 PM", "21:30"), ("10 PM", "22:00"),
    ("12 AM", "00:00"), ("12:15 pm", "12:15"), ("20:00", "20:00"),
    ("Closes 8:45 pm", "20:45"), ("", None), ("soon", None), ("25:00", None),
])
def test_clean_time(raw, want):
    assert importer.clean_time(raw) == want


def test_clean_hours_uses_closing_note_and_drops_stale_status():
    assert importer.clean_hours("10:00 AM", "", "Closes 9 pm") == ("10:00", "21:00", None, False)
    # midnight opening is a placeholder -> both unknown
    assert importer.clean_hours("00:00", "23:59", "")[:2] == (None, None)
    o, c, note, closed = importer.clean_hours("", "", "Permanently closed")
    assert closed is True and note == "Permanently closed"
    # a human-written note is kept
    assert importer.clean_hours("11:00", "19:00", "Sundays till 2")[2] == "Sundays till 2"


def test_clean_categories_handles_apostrophes_and_rejects_addresses():
    assert importer.clean_categories("['Women's clothing store']") == ["Women's clothing store"]
    assert importer.clean_categories("['Clothing store', 'menswear']") == ["Clothing store", "Menswear"]
    assert importer.clean_categories("['Shop No 172, Commercial Street']") == []
    assert importer.clean_categories("['Stalwart for iconic jeans & casualwear']") == []
    assert importer.clean_categories("['SHOPPERS STOP']") == []
    assert importer.clean_categories("[]") == []


def test_clean_row_flags_placeholder_prices_and_fixes_phone():
    row = {"id": "x-1", "name": "T", "locality_raw": "Indiranagar", "phone": "9591856690.0",
           "price_min": "300.0", "price_max": "1500.0", "lat": "12.97", "lng": "77.64",
           "geocode_precision": "rooftop", "store_type": "retail_fashion",
           "rating": "4.6", "review_count": "148",
           "notes": "Scraped from Google Maps (Boutique)"}
    v = importer.clean_row(row)
    assert v["phone"] == "9591856690" and v["price_estimated"] is True
    assert v["area"] == "Indiranagar" and v["notes"] is None
    assert v["google_rating"] == 4.6 and v["google_review_count"] == 148


def test_derive_area():
    d = importer.derive_area
    assert d("Koramangala 8th Block", None) == "Koramangala"            # seed rule
    assert d("Bengaluru", "76, 6th Main Road, 5th Block, Jayanagar, Bengaluru, Karnataka 560041") == "Jayanagar"
    assert d("114", "12, Some Rd, Yelahanka, Bengaluru, Karnataka 560064") == "Yelahanka"
    # no usable text -> nearest well-known locality to the pin
    assert d("Bengaluru", None, 12.9352, 77.6245) == "Koramangala"
    assert d("Ground Floor", None, 13.0035, 77.5710) == "Malleshwaram"  # gazetteer spelling normalised
    assert d("Bengaluru", None) == "Bengaluru"
    assert d("Bengaluru", None, 13.30, 77.90) == "Bengaluru"            # too far from anything known


def test_phone_in_address_column_is_moved():
    v = importer.clean_row({"id": "x-2", "name": "T", "locality_raw": "Bengaluru",
                            "address": "088850 45277", "lat": "12.9352", "lng": "77.6245"})
    assert v["address"] is None and v["phone"] == "088850 45277" and v["area"] == "Koramangala"


def test_score_prior_needs_enough_google_reviews():
    class St:  # minimal stand-in for a Store row
        def __init__(self, rating, count):
            self.google_rating, self.google_review_count = rating, count
    assert S.score_prior(St(5.0, 1)) is None
    assert S.score_prior(St(4.6, 148)) == 4.6
    assert S.score_prior(St(None, 500)) is None


# ------------------------------------------------------------------ import --

FIELDS = ["id", "name", "locality_raw", "city", "instagram", "phone", "open_time",
          "close_time", "timing_note", "notes", "lat", "lng", "geocode_precision",
          "stock_type", "price_min", "price_max", "categories", "verified_on",
          "store_type", "rating", "review_count", "address"]


def _write_csv(path, rows, fields=FIELDS):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


@pytest.fixture()
def db():
    ensure_schema()
    s = SessionLocal()
    yield s
    s.rollback()
    s.query(Review).filter(Review.store_id.like("imp-%")).delete(synchronize_session=False)
    s.query(Store).filter(Store.id.like("imp-%")).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_import_is_idempotent_and_fill_only(db, tmp_path):
    p = tmp_path / "stores.csv"
    _write_csv(p, [
        {"id": "imp-1", "name": "Alpha", "locality_raw": "Koramangala", "lat": "12.93",
         "lng": "77.62", "store_type": "thrift", "rating": "4.5", "review_count": "10"},
        {"id": "imp-2", "name": "No Pin", "locality_raw": "Jayanagar", "store_type": "branded"},
        {"id": "imp-3", "name": "Gone", "locality_raw": "Jayanagar", "lat": "12.9", "lng": "77.5",
         "timing_note": "Permanently closed", "store_type": "branded"},
    ])
    r1 = importer.import_stores(db, p)
    assert (r1["created"], r1["updated"]) == (3, 0)
    assert [i for i, _ in r1["no_coords"]] == ["imp-2"]
    assert [i for i, _ in r1["inactive"]] == ["imp-3"]
    db.commit()

    r2 = importer.import_stores(db, p)
    assert (r2["created"], r2["updated"], r2["unchanged"]) == (0, 0, 3)

    # A hand-moved pin and a hand-written name survive a re-import; an empty
    # field is filled; Google aggregates refresh.
    s = db.get(Store, "imp-1")
    s.lat, s.name = 12.99, "Alpha (edited)"
    db.commit()
    _write_csv(p, [{"id": "imp-1", "name": "Alpha", "locality_raw": "Koramangala",
                    "lat": "12.93", "lng": "77.62", "phone": "080 1234",
                    "store_type": "thrift", "rating": "4.7", "review_count": "12"}])
    importer.import_stores(db, p)
    db.commit()
    s = db.get(Store, "imp-1")
    assert (s.lat, s.name, s.phone, s.google_rating) == (12.99, "Alpha (edited)", "080 1234", 4.7)

    # --overwrite lets the CSV win.
    importer.import_stores(db, p, overwrite=True)
    assert (db.get(Store, "imp-1").lat, db.get(Store, "imp-1").name) == (12.93, "Alpha")

    # Permanently-closed and pin-less stores are hidden from users.
    assert has_coords(db.get(Store, "imp-1"))
    assert not has_coords(db.get(Store, "imp-2"))
    assert not has_coords(db.get(Store, "imp-3"))


def test_review_ingest_dedups_without_dates(db, tmp_path):
    sp = tmp_path / "stores.csv"
    _write_csv(sp, [{"id": "imp-1", "name": "Alpha", "locality_raw": "Koramangala",
                     "lat": "12.93", "lng": "77.62"}])
    importer.import_stores(db, sp)
    db.commit()

    rf = ["review_id", "store_id", "store_name", "author", "rating", "review_text", "date", "source"]
    rp = tmp_path / "reviews.csv"
    base = {"store_id": "imp-1", "store_name": "Alpha", "author": "Asha", "rating": "5",
            "review_text": "Great finds", "source": "google_maps"}
    _write_csv(rp, [
        {**base, "date": "2 weeks ago"},
        {**base, "date": "3 weeks ago"},                    # same review, later scrape
        {**base, "author": "Ravi", "review_text": ""},      # rating-only review
        {**base, "store_id": "nope", "store_name": "Unknown Shop"},
    ], rf)

    first = ingest_reviews.ingest_all(db, csv_path=rp)["sources"][0]
    assert (first["new"], first["skipped"], first["unmatched"]) == (2, 1, 1)
    again = ingest_reviews.ingest_all(db, csv_path=rp)["sources"][0]
    assert (again["new"], again["skipped"]) == (0, 3)
    assert db.query(Review).filter(Review.store_id == "imp-1").count() == 2


def test_relative_dates():
    ref = ingest_reviews._CSV_REF_DATE
    f = ingest_reviews._parse_relative_date
    assert (ref - f("2 weeks ago", ref)).days == 14
    assert (ref - f("a month ago", ref)).days == 30
    assert (ref - f("Edited a year ago", ref)).days == 365
    assert f("", ref) == ref


# ------------------------------------------------------------------- score --

def test_experience_score_shrinks_small_samples():
    one = S.experience_score([(5, 1.0)])
    many = S.experience_score([(5, 1.0)] * 50)
    assert one < 4.4 and many > 4.85                 # one 5-star review is not a 5.0
    assert S.experience_score([]) is None
    # A strong Google rating pulls a thin sample up; a weak one pulls it down.
    assert S.experience_score([(3, 0.0)], prior_mean=4.8) > S.experience_score([(3, 0.0)], prior_mean=2.5)


def test_experience_score_ignores_missing_text_sentiment():
    # Rating-only reviews must not drag sentiment toward neutral.
    with_blank = S.experience_score([(5, 0.9), (5, None)], prior_weight=0)
    text_only = S.experience_score([(5, 0.9), (5, 0.9)], prior_weight=0)
    assert with_blank == text_only
    assert S.experience_score([(4, None)], prior_weight=0) == 4.0


# ---------------------------------------------------------------- ensemble --

def test_to_three_class_handles_every_label_scheme():
    three = S.to_three_class([{"label": "positive", "score": .7}, {"label": "neutral", "score": .2},
                              {"label": "negative", "score": .1}])
    assert three == {"negative": .1, "neutral": .2, "positive": .7}
    five = S.to_three_class([{"label": "Very Negative", "score": .1}, {"label": "Negative", "score": .2},
                             {"label": "Neutral", "score": .1}, {"label": "Positive", "score": .2},
                             {"label": "Very Positive", "score": .4}])
    assert round(five["negative"], 2) == .3 and round(five["positive"], 2) == .6
    stars = S.to_three_class([{"label": "1 star", "score": .5}, {"label": "3 stars", "score": .25},
                              {"label": "5 stars", "score": .25}])
    assert stars == {"negative": .5, "neutral": .25, "positive": .25}
    generic = S.to_three_class([{"label": "LABEL_0", "score": .2}, {"label": "LABEL_2", "score": .8}])
    assert generic["positive"] == .8
    with pytest.raises(ValueError):
        S.to_three_class([{"label": "joy", "score": 1.0}])


def test_analyze_without_token_falls_back_to_vader(monkeypatch):
    monkeypatch.setattr(S, "hf_token", "")
    assert S.analyze("Bahut accha, great store!")[0] == "positive"
    assert S.analyze("   ") == ("neutral", 0.0)


def _fake_models(monkeypatch, answers):
    """answers: {model: probs dict | Exception}"""
    monkeypatch.setattr(S, "hf_token", "t")
    monkeypatch.setattr(S, "HF_SENTIMENT_MODELS", list(answers))

    def fake(model, text):
        a = answers[model]
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(S, "_hf_probs", fake)


def test_ensemble_soft_vote_and_partial_failure(monkeypatch):
    pos = {"negative": .1, "neutral": .1, "positive": .8}
    neg = {"negative": .6, "neutral": .3, "positive": .1}
    _fake_models(monkeypatch, {"a": pos, "b": neg})
    # averaged: neg .35 / neu .2 / pos .45 -> positive, compound +0.10
    assert S.analyze("text") == ("positive", 0.1)
    # one model down -> the other still answers
    _fake_models(monkeypatch, {"a": RuntimeError("503"), "b": neg})
    assert S.analyze("text") == ("negative", -0.5)
    # every model down -> VADER, never an exception
    _fake_models(monkeypatch, {"a": RuntimeError("503"), "b": RuntimeError("503")})
    assert S.analyze("great store")[0] == "positive"


def test_star_rating_breaks_ties_only_when_unsure(monkeypatch):
    unsure = {"negative": .30, "neutral": .40, "positive": .30}
    _fake_models(monkeypatch, {"a": unsure})
    assert S.analyze("Ekdum bakwaas", rating=None)[0] == "neutral"
    assert S.analyze("Ekdum bakwaas", rating=1)[0] == "negative"     # stars decide
    assert S.analyze("Mast hai", rating=5)[0] == "positive"
    # A confident model is never overruled by the stars.
    sure = {"negative": .9, "neutral": .05, "positive": .05}
    _fake_models(monkeypatch, {"a": sure})
    assert S.analyze("terrible", rating=5)[0] == "negative"

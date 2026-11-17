"""Regression tests for the bug / weakness sweep: each test pins one fix."""
import datetime as dt
import uuid

from app.auth import create_token, verify_password, hash_password
from app.chat import engine as chat_engine
from app.chat.places import resolve_place
from app.chat.retrieval import _extract_category, has_phrase
from app.common.hours import IST, is_open_now
from app.models import Store, StoreSimilarity, User

INDIRANAGAR = (12.9719, 77.6412)


def _store(db, sid, name="Shop", score=None, **kw):
    s = Store(id=sid, name=name, area="Indiranagar", lat=INDIRANAGAR[0], lng=INDIRANAGAR[1],
              experience_score=score, **kw)
    db.add(s)
    db.commit()
    return s


def _at(hour, minute=0):
    return dt.datetime(2026, 11, 17, hour, minute, tzinfo=IST)   # a Tuesday


# ------------------------------------------------------------- matching

def test_place_alias_matches_whole_words_only():
    assert resolve_place("sorry i meant vintage") is None          # "orr" inside "sorry"
    assert resolve_place("stores near orr").canonical


def test_category_matches_whole_words_and_plurals():
    assert _extract_category("going on a safari") is None          # "sari"
    assert _extract_category("cheap kurtas") == "ethnic"
    assert has_phrase("re store koramangala", "re store")
    assert not has_phrase("more stores", "re store")


# ------------------------------------------------------------- hours

def test_open_now_handles_past_midnight_and_padded_days():
    s = Store(id="h", name="h", area="a", open_time="18:00", close_time="01:00",
              closed_days=" Monday, Sunday")
    assert is_open_now(s, _at(23)) is True
    assert is_open_now(s, _at(0, 30)) is True
    assert is_open_now(s, _at(12)) is False
    assert is_open_now(s, _at(23) - dt.timedelta(days=1)) is False   # Monday, with a space


# ------------------------------------------------------------- auth

def test_password_check_and_bad_token_subject(client, db):
    assert verify_password("pw-123456", hash_password("pw-123456"))
    assert not verify_password("nope", hash_password("pw-123456"))
    user = User(id=999, email="x@example.com", name="X")
    token = create_token(user)                      # user is not in the DB
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_unknown_email_and_wrong_password_look_the_same(client):
    client.post("/api/auth/register", json={"name": "A", "email": "a@example.com",
                                            "password": "secret-pw"})
    wrong = client.post("/api/auth/login", json={"email": "a@example.com", "password": "nope-nope"})
    unknown = client.post("/api/auth/login", json={"email": "b@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_blank_names_and_oversized_inputs_are_rejected(client):
    r = client.post("/api/auth/register", json={"name": "   ", "email": "c@example.com",
                                                "password": "secret-pw"})
    assert r.status_code == 422
    r = client.post("/api/chat", json={"message": "hi", "session_id": "x" * 65})
    assert r.status_code == 422


# ------------------------------------------------------------- stores

def test_unscored_stores_rank_last(client, db):
    _store(db, "blr-0001", "Unscored")
    _store(db, "blr-0002", "Scored", score=4.2)
    names = [s["name"] for s in client.get("/api/recommendations").json()["stores"]]
    assert names == ["Scored", "Unscored"]


def test_similar_store_with_null_score_does_not_crash(client, db):
    _store(db, "blr-0001", "A")
    _store(db, "blr-0002", "B")
    db.add(StoreSimilarity(store_id="blr-0001", similar_id="blr-0002", rank=0, score=None))
    db.commit()
    r = client.get("/api/stores/blr-0001")
    assert r.status_code == 200 and r.json()["similar"][0]["id"] == "blr-0002"


def test_hidden_store_cannot_be_reviewed(client, db):
    _store(db, "blr-0001", "Closed", is_active=False)
    tok = client.post("/api/auth/register", json={"name": "R", "email": "r@example.com",
                                                  "password": "secret-pw"}).json()["token"]
    r = client.post("/api/stores/blr-0001/reviews", json={"rating": 5, "text": "x"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404


def test_nearby_radius_is_capped(client):
    assert client.get("/api/stores/nearby?lat=12.97&lng=77.59&radius_km=50000").status_code == 400


# ------------------------------------------------------------- chat

def test_new_search_after_a_trip_is_not_a_refinement(client, db):
    for i in range(4):
        _store(db, f"blr-000{i}", f"Thrift {i}", score=4.0, store_type="thrift", price_min=200 + i)
    sid = str(uuid.uuid4())
    first = client.post("/api/chat", json={"message": "thrift stores in Indiranagar",
                                           "session_id": sid}).json()
    assert first.get("trip")
    again = client.post("/api/chat", json={"message": "vintage under ₹500 in Indiranagar",
                                           "session_id": sid}).json()
    assert again["intent"] != "plan_refinement"


def test_advice_placeholder_never_reaches_the_user(monkeypatch, db):
    monkeypatch.setattr(chat_engine, "CHAT_ADVICE", False)
    out = chat_engine.respond("how do i check a thrifted jacket for damage", db)
    assert "__advice__" not in out["reply"]

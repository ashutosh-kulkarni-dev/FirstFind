"""Security tests for saved lists (/api/lists).

Covers authentication (missing, malformed, forged, expired and orphaned
tokens), ownership (one user can never read, change or delete another
user's list), and input handling (limits, hidden/unknown stores, hostile
strings).
"""
import datetime as dt
import uuid

import jwt
import pytest

from app.auth import create_token
from app.config import JWT_ALGO, JWT_SECRET
from app.models import SavedList, Store, User

BASE = "/api/lists"


# ------------------------------------------------------------- helpers

def _store(db, sid, lat=12.97, lng=77.59, **kw):
    db.add(Store(id=sid, name=f"Shop {sid}", area="Indiranagar", lat=lat, lng=lng, **kw))
    db.commit()


def _register(db, name="User"):
    # Created directly rather than via /api/auth/register, whose rate limit
    # (10 attempts per window) would trip across this many tests.
    user = User(name=name, email=f"{uuid.uuid4().hex[:10]}@example.com")
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_token(user)}"}, user.id


def _create(client, headers, name="Run", store_ids=("s1",), **extra):
    return client.post(BASE, headers=headers,
                       json={"name": name, "store_ids": list(store_ids), **extra})


def _token(sub, secret=JWT_SECRET, algorithm=JWT_ALGO, hours=1):
    payload = {"sub": str(sub),
               "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)}
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture()
def owner(client, db):
    """A user owning one list, plus a second user with no lists."""
    _store(db, "s1")
    _store(db, "s2")
    a_headers, a_id = _register(db, "Alice")
    b_headers, b_id = _register(db, "Bob")
    r = _create(client, a_headers, name="Alice's run", store_ids=["s1"])
    assert r.status_code == 201, r.text
    return {"a": a_headers, "b": b_headers, "a_id": a_id, "b_id": b_id,
            "list_id": r.json()["id"]}


def _every_endpoint(list_id):
    return [
        ("post", BASE, {"name": "x", "store_ids": ["s1"]}),
        ("get", BASE, None),
        ("get", f"{BASE}/{list_id}", None),
        ("patch", f"{BASE}/{list_id}", {"name": "hijacked"}),
        ("delete", f"{BASE}/{list_id}", None),
    ]


def _call(client, method, url, body, headers=None):
    kwargs = {"headers": headers or {}}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(url, **kwargs)


# ------------------------------------------------------------- authentication

@pytest.mark.parametrize("headers", [
    {},                                                  # no header
    {"Authorization": "Bearer"},                         # empty token
    {"Authorization": "Bearer not-a-jwt"},               # garbage
    {"Authorization": "Basic dXNlcjpwYXNz"},             # wrong scheme
], ids=["missing", "empty", "garbage", "basic-scheme"])
def test_every_list_endpoint_requires_auth(client, owner, headers):
    for method, url, body in _every_endpoint(owner["list_id"]):
        r = _call(client, method, url, body, headers)
        assert r.status_code == 401, f"{method.upper()} {url} -> {r.status_code}"


def test_forged_tokens_are_rejected(client, owner):
    forged = {
        "wrong secret": _token(owner["a_id"], secret="attacker-chosen-secret-0123456789"),
        "expired": _token(owner["a_id"], hours=-1),
        "alg none": jwt.encode({"sub": str(owner["a_id"])}, None, algorithm="none"),
        "non-numeric sub": _token("1 OR 1=1"),
    }
    for label, tok in forged.items():
        r = client.get(BASE, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401, f"{label}: {r.status_code}"


def test_token_for_deleted_user_is_rejected(client, db, owner):
    db.query(SavedList).filter(SavedList.user_id == owner["b_id"]).delete()
    db.query(User).filter(User.id == owner["b_id"]).delete()
    db.commit()
    assert client.get(BASE, headers=owner["b"]).status_code == 401


# ------------------------------------------------------------- ownership (IDOR)

def test_other_users_lists_are_invisible(client, owner):
    assert client.get(BASE, headers=owner["b"]).json() == []
    # Not 403: a 404 does not reveal that the list exists.
    assert client.get(f"{BASE}/{owner['list_id']}", headers=owner["b"]).status_code == 404


def test_other_user_cannot_modify_or_delete(client, db, owner):
    lid = owner["list_id"]
    r = client.patch(f"{BASE}/{lid}", headers=owner["b"],
                     json={"name": "hijacked", "add_ids": ["s2"], "remove_ids": ["s1"]})
    assert r.status_code == 404
    assert client.delete(f"{BASE}/{lid}", headers=owner["b"]).status_code == 404

    mine = client.get(f"{BASE}/{lid}", headers=owner["a"]).json()
    assert mine["name"] == "Alice's run"
    assert [s["id"] for s in mine["stores"]] == ["s1"]


def test_missing_and_foreign_ids_look_the_same(client, owner):
    foreign = client.get(f"{BASE}/{owner['list_id']}", headers=owner["b"])
    missing = client.get(f"{BASE}/999999", headers=owner["b"])
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_list_names_are_scoped_per_user(client, owner):
    # Bob may reuse Alice's list name — the uniqueness check must not leak
    # (or be blocked by) another user's data.
    assert _create(client, owner["b"], name="Alice's run").status_code == 201


def test_user_id_in_body_is_ignored(client, db, owner):
    r = client.post(BASE, headers=owner["b"],
                    json={"name": "Planted", "store_ids": ["s1"], "user_id": owner["a_id"]})
    assert r.status_code == 201
    assert db.get(SavedList, r.json()["id"]).user_id == owner["b_id"]
    assert all(lst["name"] != "Planted"
               for lst in client.get(BASE, headers=owner["a"]).json())


def test_non_integer_list_id_is_rejected(client, owner):
    for bad in ("abc", "1;DROP TABLE saved_lists", "1.5"):
        r = client.get(f"{BASE}/{bad}", headers=owner["a"])
        assert r.status_code in (404, 422), f"{bad!r} -> {r.status_code}"


# ------------------------------------------------------------- input handling

def test_hidden_and_unknown_stores_are_never_attached(client, db, owner):
    _store(db, "hidden", lat=None, lng=None)
    _store(db, "inactive", is_active=False)
    r = _create(client, owner["a"], name="Mixed",
                store_ids=["s1", "hidden", "inactive", "does-not-exist", "s1"])
    assert r.status_code == 201
    assert r.json()["store_count"] == 1          # only s1, and only once

    r = client.patch(f"{BASE}/{r.json()['id']}", headers=owner["a"],
                     json={"add_ids": ["hidden", "inactive", "does-not-exist"]})
    assert r.json()["store_count"] == 1


@pytest.mark.parametrize("body", [
    {"name": "", "store_ids": ["s1"]},
    {"name": "   ", "store_ids": ["s1"]},
    {"name": "x" * 121, "store_ids": ["s1"]},
    {"name": "ok", "store_ids": []},
    {"name": "ok", "store_ids": ["s1"] * 201},
    {"name": "ok", "store_ids": ["x" * 21]},
    {"name": "ok", "store_ids": ["s1"], "radius_km": 51},
    {"name": "ok", "store_ids": ["s1"], "radius_km": -1},
    {"name": "ok", "store_ids": ["s1"], "center_lat": 91},
    {"name": "ok", "store_ids": ["s1"], "source_label": "x" * 161},
    {"name": "ok", "store_ids": "s1"},
], ids=["empty-name", "blank-name", "long-name", "no-stores", "too-many-stores",
        "long-store-id", "huge-radius", "negative-radius", "bad-lat", "long-label",
        "store-ids-not-list"])
def test_invalid_create_bodies_are_rejected(client, owner, body):
    assert client.post(BASE, headers=owner["a"], json=body).status_code == 422


def test_patch_limits_are_enforced(client, owner):
    url = f"{BASE}/{owner['list_id']}"
    for body in ({"name": "   "}, {"add_ids": ["s1"] * 201}, {"remove_ids": ["s1"] * 201}):
        assert client.patch(url, headers=owner["a"], json=body).status_code == 422


def test_hostile_names_are_stored_verbatim(client, owner):
    for name in ("'; DROP TABLE saved_lists; --", "<script>alert(1)</script>"):
        r = _create(client, owner["a"], name=name)
        assert r.status_code == 201
        assert r.json()["name"] == name        # stored as data, not executed
    # The table is still there and holds all three lists.
    assert len(client.get(BASE, headers=owner["a"]).json()) == 3


def test_duplicate_names_conflict_for_the_same_user(client, owner):
    assert _create(client, owner["a"], name="Alice's run").status_code == 409
    other = _create(client, owner["a"], name="Second").json()["id"]
    r = client.patch(f"{BASE}/{other}", headers=owner["a"], json={"name": "Alice's run"})
    assert r.status_code == 409


def test_delete_returns_empty_204_and_removes_items(client, owner):
    r = client.delete(f"{BASE}/{owner['list_id']}", headers=owner["a"])
    assert r.status_code == 204 and r.content == b""
    assert client.get(f"{BASE}/{owner['list_id']}", headers=owner["a"]).status_code == 404

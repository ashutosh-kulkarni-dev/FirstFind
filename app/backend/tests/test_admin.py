"""Admin API: access control, store and review changes, the change log,
needs-attention, CSV export, and prune never deleting admin-added stores."""
import csv
import datetime
import io
import uuid

import pytest

from app.models import AdminAudit, Review, Store, User


def _register(client, admin: bool = False) -> dict:
    email = f"u_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/api/auth/register",
                    json={"name": "Tester", "email": email, "password": "secret12"})
    assert r.status_code == 200, r.text
    if admin:
        from app.database import SessionLocal
        db = SessionLocal()
        db.query(User).filter(User.email == email).update({"is_admin": True})
        db.commit()
        db.close()
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def admin(client):
    return _register(client, admin=True)


@pytest.fixture()
def store(db):
    s = Store(id="blr-0007", name="Love Me Twice", area="Indiranagar",
              lat=12.97, lng=77.64, is_active=True, created_via="csv", review_count=0)
    db.add(s)
    db.commit()
    return s


def test_admin_routes_need_an_admin(client, store):
    assert client.get("/api/admin/stores").status_code == 401
    user = _register(client)
    for method, url in (("get", "/api/admin/stores"), ("get", "/api/admin/attention"),
                        ("get", "/api/admin/audit"), ("get", "/api/admin/export/stores.csv"),
                        ("patch", "/api/admin/stores/blr-0007"),
                        ("delete", "/api/admin/stores/blr-0007?confirm=blr-0007")):
        kwargs = {"json": {"name": "x"}} if method == "patch" else {}
        r = getattr(client, method)(url, headers=user, **kwargs)
        assert r.status_code == 403, (url, r.status_code)


def test_me_reports_admin_flag(client):
    assert client.get("/api/auth/me", headers=_register(client)).json()["is_admin"] is False
    assert client.get("/api/auth/me", headers=_register(client, True)).json()["is_admin"] is True


def test_edit_store_writes_change_log(client, admin, store, db):
    r = client.patch("/api/admin/stores/blr-0007", headers=admin,
                     json={"name": "Love Me Twice Thrift", "tags": ["womenswear"],
                           "open_time": "11:00", "lat": 12.98, "lng": 77.65})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Love Me Twice Thrift"
    assert body["tags"] == ["womenswear"]
    assert body["geocode_precision"] == "admin"
    db.expire_all()
    s = db.get(Store, "blr-0007")
    assert s.admin_edited_at is not None and s.tags_source == "admin"
    log = client.get("/api/admin/audit", headers=admin).json()["entries"]
    assert log[0]["action"] == "update"
    assert log[0]["changes"]["name"] == ["Love Me Twice", "Love Me Twice Thrift"]
    assert log[0]["user_email"]


def test_edit_validation(client, admin, store):
    assert client.patch("/api/admin/stores/blr-0007", headers=admin,
                        json={"open_time": "25:00"}).status_code == 422
    assert client.patch("/api/admin/stores/blr-0007", headers=admin,
                        json={"tags": ["not-a-tag"]}).status_code == 422
    assert client.patch("/api/admin/stores/blr-0007", headers=admin,
                        json={"name": None}).status_code == 422
    assert client.patch("/api/admin/stores/blr-0007", headers=admin,
                        json={"lat": None}).status_code == 422   # half a pin
    assert client.patch("/api/admin/stores/blr-0007", headers=admin,
                        json={"price_min": 900, "price_max": 100}).status_code == 422


def test_hide_and_unhide_store(client, admin, store):
    r = client.patch("/api/admin/stores/blr-0007", headers=admin, json={"is_active": False})
    assert r.json()["is_active"] is False
    assert client.get("/api/stores/blr-0007").status_code == 404
    client.patch("/api/admin/stores/blr-0007", headers=admin, json={"is_active": True})
    assert client.get("/api/stores/blr-0007").status_code == 200
    actions = [e["action"] for e in client.get("/api/admin/audit", headers=admin).json()["entries"]]
    assert actions == ["unhide", "hide"]


def test_create_store_gets_next_id(client, admin, store):
    r = client.post("/api/admin/stores", headers=admin,
                    json={"name": "New Find", "area": "Jayanagar", "lat": 12.93, "lng": 77.58})
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "blr-0008"
    assert r.json()["created_via"] == "admin"
    assert client.get("/api/stores/blr-0008").status_code == 200


def test_delete_store_needs_confirmation(client, admin, store, db):
    assert client.delete("/api/admin/stores/blr-0007", headers=admin).status_code == 422
    assert client.delete("/api/admin/stores/blr-0007?confirm=wrong",
                         headers=admin).status_code == 400
    r = client.delete("/api/admin/stores/blr-0007?confirm=blr-0007", headers=admin)
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Store, "blr-0007") is None
    assert db.query(AdminAudit).filter_by(action="delete", entity_id="blr-0007").count() == 1


def _review(db, store_id="blr-0007", text="Great finds", rating=5):
    user = db.query(User).first()
    r = Review(store_id=store_id, user_id=user.id, rating=rating, text=text,
               sentiment="positive", sentiment_score=0.8)
    db.add(r)
    db.commit()
    return r.id


def test_hidden_review_disappears_everywhere(client, admin, store, db):
    rid = _review(db)
    keep = _review(db, text="Okay place", rating=3)
    r = client.patch(f"/api/admin/reviews/{rid}", headers=admin, json={"is_hidden": True})
    assert r.status_code == 200 and r.json()["is_hidden"] is True
    public = client.get("/api/stores/blr-0007").json()
    assert [x["id"] for x in public["reviews"]] == [keep]
    assert public["sentiment_summary"]["total"] == 1
    assert public["review_count"] == 1
    # still visible to admins
    assert len(client.get("/api/admin/stores/blr-0007", headers=admin).json()["reviews"]) == 2


def test_delete_review(client, admin, store, db):
    rid = _review(db)
    assert client.delete(f"/api/admin/reviews/{rid}", headers=admin).status_code == 200
    db.expire_all()
    assert db.get(Review, rid) is None


def test_needs_attention(client, admin, db):
    db.add_all([
        Store(id="blr-0001", name="EcoDhaga", area="Koramangala", lat=12.9, lng=77.6),
        Store(id="blr-0002", name="Thrift Store", area="Chandra Layout", lat=12.9, lng=77.5),
        Store(id="blr-0003", name="Escape Closet", area="JP Nagar"),            # no pin
        Store(id="blr-0004", name="Raheja Arcade", area="Koramangala", lat=12.9, lng=77.6),
        Store(id="blr-0005", name="Vintage Lane", area="BTM", lat=12.9, lng=77.6,
              google_status="not_found"),
    ])
    db.commit()
    body = client.get("/api/admin/attention", headers=admin).json()
    by_id = {it["store"]["id"]: {r["code"] for r in it["reasons"]} for it in body["items"]}
    assert "blr-0001" not in by_id
    assert by_id["blr-0002"] == {"placeholder_name"}
    assert by_id["blr-0003"] == {"no_pin"}
    assert by_id["blr-0004"] == {"placeholder_name"}
    assert by_id["blr-0005"] == {"not_on_google"}


def test_export_csv(client, admin, store):
    r = client.get("/api/admin/export/stores.csv", headers=admin)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("﻿"))))
    assert rows[0]["id"] == "blr-0007" and rows[0]["name"] == "Love Me Twice"


def test_prune_and_import_leave_admin_work_alone(db, tmp_path):
    from app.data.importer import import_stores, prune_stores
    header = "id,name,locality_raw,city,lat,lng,geocode_precision,store_type\n"
    rows = "".join(f"blr-{i:04d},Store {i},Area {i},Bengaluru,12.9,77.6,locality,thrift\n"
                   for i in range(1, 11))
    path = tmp_path / "stores.csv"
    path.write_text(header + rows, encoding="utf-8")
    import_stores(db, path)
    db.add(Store(id="blr-0011", name="Admin Added", area="HSR", lat=12.91, lng=77.64,
                 created_via="admin"))
    edited = db.get(Store, "blr-0001")
    edited.name, edited.lat = "Renamed By Admin", 12.95
    edited.admin_edited_at = datetime.datetime.utcnow()
    db.flush()

    assert prune_stores(db, path)["stores_removed"] == 0
    assert db.get(Store, "blr-0011") is not None
    import_stores(db, path, overwrite=True)
    assert db.get(Store, "blr-0001").name == "Renamed By Admin"
    assert db.get(Store, "blr-0001").lat == 12.95

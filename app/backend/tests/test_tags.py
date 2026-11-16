"""Store tags, and the kind / tag filters on the store list."""
from app.data.tags import assign_tags, derive_tags
from app.models import Review, Store, User


def test_tags_come_from_name_type_and_description():
    assert derive_tags("Passion Ladies Hub") == ["womenswear"]
    assert derive_tags("Drift House", "Men's clothing store") == ["menswear"]
    assert derive_tags("Roopam", description="Sarees and kids wear") == ["kids", "ethnic"]
    assert derive_tags("Sri Balaji Garments", "Clothing store") == []      # says nothing: no tags


def test_one_review_mention_is_not_enough():
    assert derive_tags("Corner Shop", review_texts=["Nice denim here"]) == []
    assert derive_tags("Corner Shop", review_texts=["Nice denim here", "Good jeans too"]) == ["denim"]


def test_known_chains_match_whole_names_only():
    assert derive_tags("SNITCH - Indiranagar, Bengaluru") == ["menswear"]
    assert derive_tags("Peter England Showroom") == ["menswear", "formal"]
    assert derive_tags("Nike Factory Store") == ["sportswear"]
    assert derive_tags("Arrowhead Tailors") == []                           # not the brand "Arrow"
    assert derive_tags("Pumada Fashions") == []                             # not "Puma"


def _store(db, sid, name, **kw):
    s = Store(id=sid, name=name, area="Indiranagar", lat=12.97, lng=77.64, **kw)
    db.add(s)
    return s


def test_assign_tags_leaves_admin_edits_alone(db):
    _store(db, "tg-1", "Levi's Exclusive Store")
    _store(db, "tg-2", "Levi's Outlet", tags="vintage", tags_source="admin")
    _store(db, "tg-3", "Plain Shop")
    bot = User(email="bot@example.com", name="Bot", auth_provider="system")
    db.add(bot)
    db.flush()
    db.add_all([Review(store_id="tg-3", user_id=bot.id, rating=5, text="great vintage finds"),
                Review(store_id="tg-3", user_id=bot.id, rating=4, text="proper vintage shop")])
    db.commit()

    assert assign_tags(db) == 2
    db.commit()
    assert db.get(Store, "tg-1").tags == "menswear,womenswear,denim"
    assert (db.get(Store, "tg-2").tags, db.get(Store, "tg-2").tags_source) == ("vintage", "admin")
    assert db.get(Store, "tg-3").tags == "vintage"
    assert assign_tags(db) == 0                                             # stable on a second run


def test_store_list_filters_by_kind_and_tag(db, client):
    _store(db, "tg-4", "Thrift One", store_type="thrift", tags="vintage")
    _store(db, "tg-5", "Old Row", store_type=None, tags="menswear")           # predates the column
    _store(db, "tg-6", "Brand One", store_type="branded", tags="menswear,formal")
    _store(db, "tg-7", "Hidden Brand", store_type="branded", tags="menswear", is_active=False)
    db.commit()

    def ids(**params):
        return sorted(s["id"] for s in client.get("/api/stores", params=params).json()["stores"])

    assert ids(store_type="thrift") == ["tg-4", "tg-5"]
    assert ids(store_type="branded") == ["tg-6"]
    assert ids(tag="menswear") == ["tg-5", "tg-6"]
    assert ids(tag="formal", store_type="branded") == ["tg-6"]
    assert ids(tag="wear") == []                                             # no partial tag matches
    assert client.get("/api/stores/tg-6").json()["tags"] == ["menswear", "formal"]

    f = client.get("/api/stores/facets").json()
    assert {k["value"]: k["count"] for k in f["store_types"]} == {"thrift": 2, "branded": 1}
    assert {t["value"]: t["count"] for t in f["tags"]} == {"menswear": 2, "formal": 1, "vintage": 1}
    assert f["tags"][0]["label"] == "Menswear"


def test_importer_treats_known_chains_as_brand_stores():
    from app.data.importer import clean_row
    base = {"id": "x-1", "locality_raw": "Indiranagar", "lat": "12.97", "lng": "77.64"}
    assert clean_row({**base, "name": "Peter England", "store_type": "retail_fashion"})["store_type"] == "branded"
    assert clean_row({**base, "name": "Roopam Sarees", "store_type": "retail_fashion"})["store_type"] == "retail_fashion"
    assert clean_row({**base, "name": "Levi's Thrift Corner", "store_type": "thrift"})["store_type"] == "thrift"

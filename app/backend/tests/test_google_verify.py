"""Candidate verification + the Google review fetch, with a fake Places client.

No network: FakePlaces stands in for PlacesClient, returning responses shaped
like the Places API (New).
"""
from datetime import datetime

import pytest

from app import verify_candidates as V
from app.database import SessionLocal, ensure_schema
from app.ml import ingest_reviews
from app.ml.google_places import PlacesBudgetExceeded, parse_reviews
from app.models import Review, Store


def place(pid, name, lat, lng, status="OPERATIONAL", reviews=(), rating=4.4, count=120):
    return {
        "id": pid, "displayName": {"text": name}, "formattedAddress": f"{name}, Bengaluru",
        "location": {"latitude": lat, "longitude": lng}, "businessStatus": status,
        "rating": rating, "userRatingCount": count,
        "editorialSummary": {"text": "Casual menswear chain."},
        "primaryTypeDisplayName": {"text": "Clothing store"},
        "nationalPhoneNumber": "080 1234 5678",
        "reviews": [{"rating": r, "originalText": {"text": t},
                     "authorAttribution": {"displayName": a},
                     "publishTime": "2026-10-21T08:30:00Z"} for a, r, t in reviews],
    }


class FakePlaces:
    def __init__(self, search=None, details=None, max_calls=1000):
        self._search, self._details = search or {}, details or {}
        self.calls, self.max_calls = 0, max_calls

    def _tick(self):
        if self.calls >= self.max_calls:
            raise PlacesBudgetExceeded("cap")
        self.calls += 1

    def search_text(self, query, lat, lng, fields, radius_m=500, page_size=5):
        self._tick()
        for needle, places in self._search.items():
            if needle.lower() in query.lower():
                return places
        return []

    def details(self, place_id, fields):
        self._tick()
        return self._details[place_id]


def cand(osm_id, name, lat=12.9700, lng=77.6400, brand="", store_type="branded"):
    row = {"osm_id": osm_id, "name": name, "brand": brand, "store_type": store_type,
           "locality_raw": "Indiranagar", "address": "", "lat": str(lat), "lng": str(lng),
           "open_time": "", "close_time": "", "phone": ""}
    row.update({c: "" for c in V.RESULT_COLS})
    return row


# ------------------------------------------------------------------ matching --

def test_name_similarity_tolerates_suffixes_and_typos():
    assert V.name_similarity("Peter England", "Peter England - Rajajinagar, Bengaluru") == 1.0
    assert V.name_similarity("Balckberrys", "Blackberrys") >= V.MIN_NAME_SIMILARITY
    assert V.name_similarity("Preethi Textiles", "Gupta's Textiles") < V.MIN_NAME_SIMILARITY


def test_pick_match_requires_near_pin_matching_name_and_open():
    c = cand("node/1", "Peter England")
    near = place("p1", "Peter England - Indiranagar", 12.9701, 77.6401)
    far = place("p2", "Peter England - Jayanagar", 12.9300, 77.5800)
    other = place("p3", "Some Other Shop", 12.9700, 77.6400)
    assert V.pick_match(c, [far, other, near])[:2] == ("verified", near)
    assert V.pick_match(c, [far, other])[0] == "not_found"
    shut = place("p4", "Peter England", 12.9700, 77.6400, status="CLOSED_PERMANENTLY")
    assert V.pick_match(c, [shut])[0] == "closed"
    # a misspelt independent still matches through its brand
    assert V.pick_match(cand("node/2", "Luois Phillepe", brand="Louis Philippe"),
                        [place("p5", "Louis Philippe", 12.9700, 77.6400)])[0] == "verified"


def test_parse_reviews_prefers_original_text():
    out = parse_reviews({"reviews": [{"rating": 5, "text": {"text": "translated"},
                                      "originalText": {"text": "Bahut accha"},
                                      "authorAttribution": {"displayName": "Asha"},
                                      "publishTime": "2026-10-21T08:30:00Z"}]})
    assert out == [{"author": "Asha", "rating": 5, "text": "Bahut accha",
                    "created_at": datetime(2026, 10, 21, 8, 30)}]


# ---------------------------------------------------------- verify + promote --

def test_verify_then_promote():
    cands = [cand("node/1", "Peter England"), cand("node/2", "Ghost Boutique"),
             cand("node/3", "Shut Shop"), cand("node/4", "Zudio", lat=12.9352, lng=77.6245)]
    client = FakePlaces(search={
        "Peter England": [place("p1", "Peter England - Indiranagar", 12.9701, 77.6401,
                                reviews=[("Asha", 5, "Great shirts"), ("Ravi", 2, "Bekaar service")])],
        "Shut Shop": [place("p3", "Shut Shop", 12.9700, 77.6400, status="CLOSED_PERMANENTLY")],
        "Zudio": [place("p4", "Zudio", 12.9352, 77.6245)],
    })
    sidecar = {}
    tally = V.verify(client, cands, limit=10, reviews=sidecar)
    assert dict(tally) == {"verified": 2, "not_found": 1, "closed": 1}
    assert cands[0]["place_id"] == "p1" and cands[0]["description"] == "Casual menswear chain."
    assert len(sidecar["node/1"]) == 2 and "node/3" not in sidecar

    # A second run skips rows already checked: no extra (billed) calls.
    before = client.calls
    assert sum(V.verify(client, cands, limit=10, reviews=sidecar).values()) == 0
    assert client.calls == before

    stores = [{"id": "blr-0576", "name": "Old Store", "lat": "12.90", "lng": "77.50"},
              {"id": "blr-0200", "name": "Zudio - Koramangala", "lat": "12.9353", "lng": "77.6246"}]
    fields = ["id", "name", "locality_raw", "city", "phone", "open_time", "close_time", "notes",
              "lat", "lng", "geocode_precision", "categories", "verified_on", "store_type",
              "rating", "review_count", "address"]
    review_rows = [{"review_id": "rev-0001"}]
    new_stores, new_reviews = V.promote(cands, stores, fields, sidecar, review_rows)

    assert [s["id"] for s in new_stores] == ["blr-0577"]          # next free id
    s = new_stores[0]
    assert s["name"] == "Peter England - Indiranagar" and s["google_place_id"] == "p1"
    assert s["categories"] == "['Clothing store']" and s["rating"] == 4.4
    assert "google_place_id" in fields and "description" in fields
    assert [(r["store_id"], r["author"], r["date"]) for r in new_reviews] == [
        ("blr-0577", "Asha", "2026-10-21"), ("blr-0577", "Ravi", "2026-10-21")]
    # Zudio is already in our data 15 m away -> duplicate, not promoted.
    assert cands[3]["verified"] == "duplicate" and not cands[3]["promoted_id"]
    assert cands[1]["promoted_id"] == "" and cands[2]["promoted_id"] == ""
    # Promoting again adds nothing.
    assert V.promote(cands, stores, fields, sidecar, review_rows) == ([], [])


def test_verify_respects_limit():
    cands = [cand(f"node/{i}", f"Shop {i}") for i in range(5)]
    client = FakePlaces()
    assert sum(V.verify(client, cands, limit=2).values()) == 2
    assert client.calls == 2 and sum(1 for c in cands if c["verified"]) == 2


# ------------------------------------------------------ weekly Google ingest --

@pytest.fixture()
def db():
    ensure_schema()
    s = SessionLocal()
    yield s
    s.rollback()
    s.query(Review).filter(Review.store_id.like("gg-%")).delete(synchronize_session=False)
    s.query(Store).filter(Store.id.like("gg-%")).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_google_ingest_rotates_dedups_and_refreshes(db):
    # Park every other store as "fetched just now" so only gg-* are due.
    for s in db.query(Store).all():
        s.reviews_fetched_at = datetime.utcnow()
    db.add_all([
        Store(id="gg-1", name="Alpha Wear", area="Indiranagar", lat=12.97, lng=77.64,
              reviews_fetched_at=datetime(2026, 11, 1)),
        Store(id="gg-2", name="Beta Wear", area="Indiranagar", lat=12.97, lng=77.64),       # never fetched
        Store(id="gg-3", name="No Pin", area="Indiranagar"),                                # hidden
        Store(id="gg-4", name="Gamma Wear", area="Indiranagar", lat=12.97, lng=77.64,
              reviews_fetched_at=datetime(2026, 10, 1), google_place_id="pg"),
    ])
    db.commit()
    bot = ingest_reviews._get_or_create_bot(db)
    client = FakePlaces(
        search={"Alpha Wear": [{"id": "pa"}], "Beta Wear": [{"id": "pb"}]},
        details={
            "pa": place("pa", "Alpha Wear", 12.97, 77.64, reviews=[("Asha", 5, "Lovely")]),
            "pb": place("pb", "Beta Wear", 12.97, 77.64, rating=3.9, count=40,
                        reviews=[("Ravi", 4, "Good"), ("Ravi", 4, "Good")]),
            "pg": place("pg", "Gamma Wear", 12.97, 77.64, status="CLOSED_PERMANENTLY"),
        },
        max_calls=3)   # enough for gg-2 (search + details) and gg-4 (details), not gg-1

    r = ingest_reviews.ingest_from_google(db, bot, limit=3, client=client)
    db.commit()
    # Order: never-fetched gg-2 first, then oldest gg-4; gg-1 hits the cap; gg-3 skipped.
    assert (r["stores_visited"], r["new"], r["skipped"]) == (2, 1, 1)
    b = db.get(Store, "gg-2")
    assert (b.google_place_id, b.google_rating, b.google_review_count) == ("pb", 3.9, 40)
    assert b.reviews_fetched_at is not None
    assert db.get(Store, "gg-4").is_active is False                 # Google says closed for good
    assert db.get(Store, "gg-1").reviews_fetched_at == datetime(2026, 11, 1)   # untouched
    assert db.get(Store, "gg-3").reviews_fetched_at is None

    # Next run: gg-1 is now the stalest and gets its turn; nothing duplicates.
    client.max_calls = 100
    r2 = ingest_reviews.ingest_from_google(db, bot, limit=1, client=client)
    db.commit()
    assert (r2["stores_visited"], r2["new"]) == (1, 1)
    assert db.query(Review).filter(Review.store_id.like("gg-%")).count() == 2


def test_iso_dates_are_kept():
    assert ingest_reviews._parse_relative_date("2026-10-21") == datetime(2026, 10, 21)


def test_google_ingest_stops_at_details_cap(db, monkeypatch):
    """The free-tier guard: never more than INGEST_MAX_DETAILS review fetches per run."""
    for s in db.query(Store).all():
        s.reviews_fetched_at = datetime.utcnow()
    db.add_all([Store(id=f"gg-{i}", name=f"Cap Shop {i}", area="Indiranagar", lat=12.97,
                      lng=77.64, google_place_id=f"pc{i}") for i in (5, 6, 7)])
    db.commit()
    bot = ingest_reviews._get_or_create_bot(db)
    client = FakePlaces(details={f"pc{i}": place(f"pc{i}", f"Cap Shop {i}", 12.97, 77.64)
                                 for i in (5, 6, 7)})
    monkeypatch.setattr(ingest_reviews, "INGEST_MAX_DETAILS", 2)
    r = ingest_reviews.ingest_from_google(db, bot, client=client)
    assert r["stores_visited"] == 2 and client.calls == 2


# ------------------------------------------- near misses, manual adds, daily --

def test_not_found_records_the_near_miss():
    c = cand("node/9", "Biba")
    status, _, _, miss = V.pick_match(c, [place("p", "Biba - Forum Mall", 12.9900, 77.6400)])
    assert status == "not_found" and "Biba - Forum Mall" in miss and "too far" in miss
    status, _, _, miss = V.pick_match(c, [place("p", "W for Woman", 12.9700, 77.6400)])
    assert status == "not_found" and "name differs" in miss
    assert V.pick_match(c, [])[3] == ""


def test_hand_added_store_is_checked_first_and_matched_without_a_pin():
    cands = [cand("node/1", "Bulk Shop")]
    row = V.add_candidate(cands, "Tibetan Plaza Thrift", area="Indiranagar", store_type="thrift")
    assert row["osm_id"] == "manual/1" and row["lat"] == "" and row["verified"] == ""
    assert [c["name"] for c in V.unchecked(cands)] == ["Tibetan Plaza Thrift", "Bulk Shop"]

    client = FakePlaces(search={"Tibetan Plaza": [place("pt", "Tibetan Plaza Thrift Store", 12.98, 77.61)]})
    sidecar = {}
    tally = V.verify(client, V.unchecked(cands), limit=1, reviews=sidecar)
    assert dict(tally) == {"verified": 1}
    assert row["place_id"] == "pt" and row["match_km"] == "" and "manual/1" in sidecar
    assert cands[0]["verified"] == ""          # the bulk row waits for the next run


def test_google_ingest_stops_when_key_returns_no_reviews(db):
    for s in db.query(Store).all():
        s.reviews_fetched_at = datetime.utcnow()
    ids = range(10, 18)
    db.add_all([Store(id=f"gg-{i}", name=f"Mute Shop {i}", area="Indiranagar", lat=12.97,
                      lng=77.64, google_place_id=f"pm{i}") for i in ids])
    db.commit()
    bot = ingest_reviews._get_or_create_bot(db)
    client = FakePlaces(details={f"pm{i}": place(f"pm{i}", f"Mute Shop {i}", 12.97, 77.64,
                                                 count=300) for i in ids})   # 300 ratings, 0 reviews
    r = ingest_reviews.ingest_from_google(db, bot, client=client)
    assert r["reviews_unavailable"] is True and r["stores_visited"] == 5 and client.calls == 5


def test_daily_job_shares_one_google_budget(db, tmp_path, monkeypatch):
    from app import daily_job, importer

    fields = ["id", "name", "locality_raw", "city", "instagram", "phone", "open_time",
              "close_time", "timing_note", "notes", "lat", "lng", "geocode_precision",
              "stock_type", "price_min", "price_max", "categories", "verified_on",
              "store_type", "rating", "review_count", "address"]
    stores_csv, reviews_csv = tmp_path / "stores.csv", tmp_path / "reviews.csv"
    V.write_csv(stores_csv, [{"id": "gg-900", "name": "Seed Store", "locality_raw": "Indiranagar",
                              "lat": "12.90", "lng": "77.50", "store_type": "thrift"}], fields)
    V.write_csv(reviews_csv, [{"review_id": "rev-0001", "store_id": "gg-900", "store_name": "Seed Store",
                               "author": "Asha", "rating": "5", "review_text": "Lovely", "date": "a week ago",
                               "source": "google_maps"}],
                ["review_id", "store_id", "store_name", "author", "rating", "review_text", "date", "source"])
    cands = [cand(f"node/{i}", f"Daily Shop {i}") for i in range(3)]
    V.write_csv(tmp_path / "cands.csv", cands, V.BASE_COLS + V.RESULT_COLS)

    for mod, name, path in [(V, "CANDIDATES_CSV", tmp_path / "cands.csv"),
                            (V, "CANDIDATE_REVIEWS_JSON", tmp_path / "side.json"),
                            (V, "STORES_CSV", stores_csv), (V, "REVIEWS_CSV", reviews_csv),
                            (importer, "STORES_CSV", stores_csv),
                            (ingest_reviews, "REVIEWS_CSV", reviews_csv)]:
        monkeypatch.setattr(mod, name, path)
    monkeypatch.setattr(daily_job, "GOOGLE_PLACES_API_KEY", "test-key")
    for s in db.query(Store).all():
        s.reviews_fetched_at = datetime.utcnow()
    db.commit()

    client = FakePlaces(search={"Daily Shop 0": [place("d0", "Daily Shop 0", 12.9700, 77.6400)],
                                "Daily Shop 1": [place("d1", "Daily Shop 1", 12.9700, 77.6400)]})
    import app.ml.google_places as GP
    monkeypatch.setattr(GP, "PlacesClient", lambda max_calls: setattr(client, "max_calls", max_calls) or client)

    # Budget 2: both calls go to verification; nothing is left for the review fetch.
    out = daily_job.run(budget=2)
    assert out["candidates"]["checked"] == {"verified": 2} and out["candidates"]["backlog"] == 1
    assert out["candidates"]["stores_added"] == 2 and out["google_calls_used"] == 2
    assert [s["source"] for s in out["reviews"]["sources"]] == ["csv"]
    new_ids = [r["id"] for r in V.read_csv(stores_csv)[0]]
    assert new_ids == ["gg-900", "blr-0001", "blr-0002"]
    assert out["reviews"]["total_in_db"] >= 1

    # cleanup rows this test created
    db.rollback()
    for sid in ("gg-900",):
        db.query(Review).filter(Review.store_id == sid).delete(synchronize_session=False)
        db.query(Store).filter(Store.id == sid).delete(synchronize_session=False)
    db.query(Store).filter(Store.google_place_id.in_(["d0", "d1"])).delete(synchronize_session=False)
    db.commit()


def test_verify_survives_a_google_error():
    """A quota/HTTP error must not crash the daily job or mark the row checked."""
    class Broken(FakePlaces):
        def search_text(self, *a, **k):
            raise RuntimeError("429 quota exceeded")
    cands = [cand("node/1", "Peter England")]
    assert sum(V.verify(Broken(), cands, limit=5).values()) == 0
    assert cands[0]["verified"] == ""

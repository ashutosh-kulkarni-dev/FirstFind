"""Store descriptions: Google line > AI summary > plain template. Offline."""
import pytest

from app import importer
from app.database import SessionLocal, ensure_schema
from app.ml import descriptions as D
from app.models import Review, Store, User
from app.utils import store_to_dict


def test_blurb_from_categories_keeps_google_lines_rejects_addresses():
    f = importer.blurb_from_categories
    assert f("['Stalwart for iconic jeans & casualwear']") == "Stalwart for iconic jeans & casualwear."
    assert f("['Designer polos with crocodile logos']") == "Designer polos with crocodile logos."
    assert f("['Clothing store']") is None
    assert f("['Shop No 172, Commercial Street']") is None
    assert f("['First floor, Garuda Mall, Shop No 112, Magrath Rd, near by Levi's Store']") is None
    assert f("[]") is None


def test_importer_marks_google_description_source():
    v = importer.clean_row({"id": "x-9", "name": "Levi's", "locality_raw": "Indiranagar",
                            "categories": "['Stalwart for iconic jeans & casualwear']"})
    assert v["description_source"] == "google" and v["description"].startswith("Stalwart")
    assert v["categories"] == ""            # the blurb is not also a category
    plain = importer.clean_row({"id": "x-8", "name": "Shop", "locality_raw": "Indiranagar",
                                "categories": "['Clothing store']"})
    assert plain["description"] is None and plain["description_source"] is None


def test_template_description():
    s = Store(id="t-1", name="A", area="Koramangala", store_type="thrift", categories="")
    assert D.template_description(s) == "Thrift and second-hand clothing store in Koramangala, Bengaluru."
    s = Store(id="t-2", name="B", area="Bengaluru", store_type="retail_fashion",
              categories="Boutique,Bridal shop")
    assert D.template_description(s) == "Boutique in Bengaluru. Also listed under: bridal shop."
    s = Store(id="t-3", name="C", area="Jayanagar", store_type="branded", categories="Menswear")
    assert D.template_description(s) == ("Branded clothing store in Jayanagar, Bengaluru. "
                                         "Also listed under: menswear.")


def test_describe_and_serializer_label_the_source():
    s = Store(id="t-4", name="D", area="Jayanagar", store_type="thrift", categories="")
    assert D.describe(s)[1] == "auto"
    assert store_to_dict(s)["description_source"] == "auto"
    s.description, s.description_source = "Vintage denim and jackets.", "ai"
    d = store_to_dict(s)
    assert (d["description"], d["description_source"]) == ("Vintage denim and jackets.", "ai")


@pytest.fixture()
def db():
    ensure_schema()
    s = SessionLocal()
    yield s
    s.rollback()
    s.query(Review).filter(Review.store_id.like("ds-%")).delete(synchronize_session=False)
    s.query(Store).filter(Store.id.like("ds-%")).delete(synchronize_session=False)
    s.commit()
    s.close()


def test_generate_descriptions_only_fills_gaps(db, monkeypatch):
    user = db.query(User).first()
    if user is None:
        user = User(email="ds@test.local", name="T")
        db.add(user)
        db.flush()
    db.add_all([
        Store(id="ds-1", name="Many Reviews", area="Indiranagar", lat=1, lng=1),
        Store(id="ds-2", name="One Review", area="Indiranagar", lat=1, lng=1),
        Store(id="ds-3", name="Has Google Line", area="Indiranagar", lat=1, lng=1,
              description="Casualwear for men & women.", description_source="google"),
        Store(id="ds-4", name="Closed", area="Indiranagar", lat=1, lng=1, is_active=False),
    ])
    for sid, n in (("ds-1", 3), ("ds-2", 1), ("ds-3", 3), ("ds-4", 3)):
        for i in range(n):
            db.add(Review(store_id=sid, user_id=user.id, rating=5, text=f"Nice jackets {i}"))
    db.add(Review(store_id="ds-2", user_id=user.id, rating=4, text=""))   # rating-only: not text
    db.commit()

    # No key -> stage is a no-op.
    monkeypatch.setattr(D, "GROQ_API_KEY", "")
    assert D.generate_descriptions(db) == 0

    monkeypatch.setattr(D, "GROQ_API_KEY", "test-key")
    seen = []

    def fake(store, texts, timeout=20.0):
        seen.append((store.id, len(texts)))
        return "Sells jackets and denim. Shoppers like the range."
    monkeypatch.setattr(D, "ai_description", fake)

    # Park every other store so the batch limit applies to ours only.
    others = [s for s in db.query(Store).all() if not s.id.startswith("ds-") and not s.description]
    for s in others:
        s.description = "x"
    assert D.generate_descriptions(db, limit=5) == 1
    for s in others:
        s.description = None
    assert seen == [("ds-1", 3)]                       # ds-2 too few, ds-3 has Google's, ds-4 closed
    s1 = db.get(Store, "ds-1")
    assert (s1.description_source, s1.description) == ("ai", "Sells jackets and denim. Shoppers like the range.")
    assert db.get(Store, "ds-3").description_source == "google"
    assert db.get(Store, "ds-2").description is None


def test_ai_description_rejects_odd_output(monkeypatch):
    monkeypatch.setattr(D, "GROQ_API_KEY", "test-key")

    class R:
        def __init__(self, text): self._t = text
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": self._t}}]}

    s = Store(id="t-5", name="E", area="Jayanagar", store_type="thrift", categories="")
    monkeypatch.setattr(D.httpx, "post", lambda *a, **k: R("Sells vintage denim. Shoppers praise the prices."))
    assert D.ai_description(s, ["Great denim"]) == "Sells vintage denim. Shoppers praise the prices."
    monkeypatch.setattr(D.httpx, "post", lambda *a, **k: R("Line one\nLine two\n- bullet"))
    assert D.ai_description(s, ["Great denim"]) is None
    monkeypatch.setattr(D.httpx, "post", lambda *a, **k: R("ok"))
    assert D.ai_description(s, ["Great denim"]) is None
    assert D.ai_description(s, []) is None             # nothing to summarise -> no call

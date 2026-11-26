"""Assistant: shopping slots, clarifying questions, remembered answers, trip
routes, and short replies."""
import json
import uuid

import pytest

from app.chat.route import order, plan
from app.chat.slots import extract, parse_answer, tier_of
from app.models import Store, User

INDIRANAGAR = (12.9719, 77.6412)


# ----------------------------------------------------------------- slots

@pytest.mark.parametrize("text,kind,audience,style,tier", [
    ("vintage thrift stores for women", "thrift", "womenswear", "vintage", None),
    ("brand stores for men under 2000", "branded", "menswear", None, "mid"),
    ("cheap kurtas for my wife", None, "womenswear", "ethnic", "budget"),
    ("something for my son", None, "kids", None, None),
    ("premium boutiques", "retail_fashion", None, None, "premium"),
    ("under 500", None, None, None, "budget"),
])
def test_extract_slots(text, kind, audience, style, tier):
    hits = extract(text, 2000 if "2000" in text else 500 if "500" in text else None)
    assert (hits.store_kind, hits.audience, hits.style, hits.price_tier) == (kind, audience, style, tier)


def test_parse_answer():
    assert parse_answer("price_tier", "Mid-range · ₹700–2,000") == (True, "mid")
    assert parse_answer("price_tier", "something cheap") == (True, "budget")
    assert parse_answer("audience", "for my husband") == (True, "menswear")
    assert parse_answer("audience", "skip") == (True, None)
    assert parse_answer("audience", "what's open now?") == (False, None)


def test_tier_of_uses_real_prices_only():
    s = Store(id="x", name="x", area="a", store_type="branded", price_min=300, price_max=1500,
              price_estimated=True)
    assert tier_of(s) is None                      # a generic estimate says nothing
    s.store_type = "thrift"
    assert tier_of(s) == "budget"                  # thrift is budget by nature
    s.price_estimated, s.store_type, s.price_min, s.price_max = False, "branded", 1500, 4000
    assert tier_of(s) == "premium"


# ----------------------------------------------------------------- routes

def test_route_order_is_short():
    start = (0.0, 0.0)
    pts = [(0.0, 0.03), (0.0, 0.01), (0.0, 0.02)]
    assert order(start, pts) == [1, 2, 0]


def test_plan_keeps_stops_near_the_start():
    near = [Store(id=f"n{i}", name=f"Near {i}", area="A", lat=12.9719 + i * 0.001, lng=77.6412)
            for i in range(4)]
    far = Store(id="far", name="Far", area="B", lat=13.05, lng=77.6412)
    r = plan(INDIRANAGAR, "Indiranagar", [far, *near])
    assert [s.id for s in r.stops] == ["n0", "n1", "n2", "n3"]
    assert r.total_m > 0 and all(s.walk_min >= 1 for s in r.stops)


# --------------------------------------------------------------- the chat

def _stores(db):
    rows = [
        ("blr-0001", "Love Me Twice", "thrift", "womenswear,vintage", 0.000, 0.000),
        ("blr-0002", "Pretty Little Fits", "thrift", "womenswear", 0.002, 0.001),
        ("blr-0003", "Drift House", "thrift", "menswear", 0.003, -0.002),
        ("blr-0004", "Kid Corner", "retail_fashion", "kids", -0.002, 0.002),
        ("blr-0005", "Banana Club", "branded", "menswear", 0.004, 0.003),
        ("blr-0006", "Sevens", "thrift", "vintage", -0.003, -0.001),
    ]
    for sid, name, kind, tags, dlat, dlng in rows:
        db.add(Store(id=sid, name=name, area="Indiranagar", store_type=kind, tags=tags,
                     lat=INDIRANAGAR[0] + dlat, lng=INDIRANAGAR[1] + dlng, experience_score=4.0))
    db.commit()


def _chat(client, msg, sid, headers=None, **extra):
    r = client.post("/api/chat", json={"message": msg, "session_id": sid, **extra}, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_vague_request_asks_budget_then_who(client, db):
    _stores(db)
    sid = str(uuid.uuid4())
    r = _chat(client, "show me some stores", sid)
    assert r["intent"] == "clarify" and r["clarify"]["slot"] == "price_tier"
    assert r["clarify"]["skip"] == "Skip" and len(r["clarify"]["options"]) == 3
    r = _chat(client, "Budget · under ₹700", sid, answer={"slot": "price_tier", "value": "budget"})
    assert r["clarify"]["slot"] == "audience"
    r = _chat(client, "Men", sid, answer={"slot": "audience", "value": "menswear"})
    assert r["intent"] != "clarify" and r["stores"]
    assert r["stores"][0]["id"] == "blr-0003"            # the menswear thrift shop
    assert all("womenswear" not in s["tags"] or "menswear" in s["tags"] for s in r["stores"])
    assert "for men" in r["reply"]


def test_specific_request_asks_nothing(client, db):
    _stores(db)
    r = _chat(client, "vintage thrift stores for women in Indiranagar", str(uuid.uuid4()))
    assert r["intent"] != "clarify" and "clarify" not in r
    assert r["stores"][0]["id"] == "blr-0001"


def test_skip_and_at_most_two_questions(client, db):
    _stores(db)
    sid = str(uuid.uuid4())
    _chat(client, "stores in Indiranagar", sid)
    r = _chat(client, "Skip", sid, answer={"slot": "price_tier", "value": None})
    assert r["clarify"]["slot"] == "audience"
    r = _chat(client, "Skip", sid, answer={"slot": "audience", "value": None})
    assert r["intent"] == "find_by_area" and r["stores"]


def test_new_question_instead_of_an_answer(client, db):
    _stores(db)
    sid = str(uuid.uuid4())
    _chat(client, "show me stores", sid)
    r = _chat(client, "compare Love Me Twice and Sevens", sid)
    assert r["intent"] == "store_comparison"


def test_answers_are_remembered_across_visits(client, db):
    _stores(db)
    reg = client.post("/api/auth/register", json={"name": "A", "email": f"a{uuid.uuid4().hex[:6]}@example.com",
                                                  "password": "secret12"}).json()
    auth = {"Authorization": f"Bearer {reg['token']}"}
    sid = str(uuid.uuid4())
    _chat(client, "find stores", sid, auth)
    _chat(client, "budget", sid, auth)
    _chat(client, "women", sid, auth)
    db.expire_all()
    saved = json.loads(db.get(User, reg["id"]).chat_prefs)
    assert saved == {"price_tier": "budget", "audience": "womenswear"}
    # A new visit (new chat session): no questions, the answers apply.
    r = _chat(client, "stores in Indiranagar", str(uuid.uuid4()), auth)
    assert r["intent"] == "find_by_area"
    assert "budget-friendly" in r["reply"] and "for women" in r["reply"]
    # ...until the user asks to forget them.
    _chat(client, "forget my preferences", str(uuid.uuid4()), auth)
    db.expire_all()
    assert db.get(User, reg["id"]).chat_prefs is None


def test_trip_from_area_is_a_route_with_metro(client, db):
    _stores(db)
    r = _chat(client, "plan a thrift walk in Indiranagar", str(uuid.uuid4()))
    assert r["intent"] == "plan_trip"
    route = r["route"]
    assert 3 <= len(route["stops"]) <= 5
    assert [s["id"] for s in r["stores"]] == [s["id"] for s in route["stops"]]
    assert route["start_metro"]["name"]                 # from the metro asset
    assert r["reply"].splitlines()[1].startswith("1. ")
    assert len(r["map"]["route"]) == len(route["stops"]) + 1


def test_trip_without_a_start_asks_where(client, db):
    _stores(db)
    sid = str(uuid.uuid4())
    r = _chat(client, "plan a shopping trip", sid)
    assert r["clarify"]["slot"] == "start" and r["clarify"]["skip"] is None
    assert r["clarify"]["options"][0]["value"] == "here"
    # Location refused: ask for an area, then plan from it.
    r = _chat(client, "📍 Use my location", sid, answer={"slot": "start", "value": "here"})
    assert r["intent"] == "clarify" and all(o["value"] != "here" for o in r["clarify"]["options"])
    r = _chat(client, "Indiranagar", sid)
    assert r["intent"] == "plan_trip" and r["route"]["stops"]


def test_trip_from_my_location(client, db):
    _stores(db)
    sid = str(uuid.uuid4())
    _chat(client, "plan me a thrift walk", sid)
    r = _chat(client, "📍 Use my location", sid, answer={"slot": "start", "value": "here"},
              origin={"lat": INDIRANAGAR[0], "lng": INDIRANAGAR[1]})
    assert r["intent"] == "plan_trip"
    assert r["route"]["start_label"] == "where you are"


def test_replies_are_short(client, db):
    _stores(db)
    for msg in ["vintage thrift stores for women in Indiranagar", "what's open now?", "hi",
                "brand stores for men under 2000"]:
        r = _chat(client, msg, str(uuid.uuid4()))
        first_line = r["reply"].split("\n")[0]
        assert len(first_line.split()) <= 30, first_line

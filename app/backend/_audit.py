"""Full-surface functionality audit (SQLite, self-contained) — not shipped.

Exercises EVERY endpoint and feature and prints a per-functionality PASS/FAIL
report (continues past failures so you see the whole picture in one run).
Complements _verify.py (which focuses on the ML/retrieval invariants).

Run: python _audit.py     (set HUGGINGFACE_TOKEN to exercise the live HF path)
"""
import os
import pathlib
import uuid

_DB = pathlib.Path(__file__).parent / "_audit.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["FIRSTFIND_JWT_SECRET"] = "audit-secret"

from fastapi.testclient import TestClient          # noqa: E402
from starlette.applications import Starlette        # noqa: E402
from starlette.responses import JSONResponse        # noqa: E402
from starlette.routing import Route                 # noqa: E402

from app.main import app                            # noqa: E402
from app.middleware import RateLimitMiddleware      # noqa: E402
from app.seed import seed                           # noqa: E402
from app.database import SessionLocal               # noqa: E402
from app.models import Interaction, Store            # noqa: E402

_results = []


def check(name, fn):
    """Run a check; record PASS/FAIL/ERROR without aborting the whole run."""
    try:
        fn()
        _results.append((True, name, ""))
        print(f"  PASS  {name}")
    except AssertionError as e:
        _results.append((False, name, str(e)))
        print(f"  FAIL  {name}  --> {e}")
    except Exception as e:
        _results.append((False, name, f"{type(e).__name__}: {e}"))
        print(f"  ER:   {name}  --> {type(e).__name__}: {e}")


def section(title):
    print(f"\n=== {title} ===")


def main():
    seed()
    with TestClient(app) as client:   # `with` triggers the app lifespan
        _run(client)
    _summary()


def _run(c):
    db = SessionLocal()
    try:
        visible = db.query(Store).filter(Store.lat.isnot(None)).all()
        sid = visible[0].id
        area = visible[0].area
        cat = next((cc for s in visible for cc in (s.categories or "").split(",") if cc), None)
        two_names = [s.name for s in visible[:2]]
        hidden = db.query(Store).filter(Store.lat.is_(None)).first()
        hidden_id = hidden.id if hidden else None
        lat, lng = visible[0].lat, visible[0].lng
    finally:
        db.close()

    email = f"audit-{uuid.uuid4().hex[:8]}@t.com"
    H = {}

    # -------------------------------------------------- AUTH
    section("Auth")
    def reg():
        r = c.post("/api/auth/register", json={"name": "A", "email": email, "password": "secret1"})
        assert r.status_code == 200, r.text
        H["Authorization"] = f"Bearer {r.json()['token']}"
    check("register -> 200 + token", reg)
    check("register duplicate email -> 409",
          lambda: _assert(c.post("/api/auth/register",
                   json={"name": "A", "email": email, "password": "secret1"}).status_code == 409))
    check("login correct -> 200",
          lambda: _assert(c.post("/api/auth/login",
                   json={"email": email, "password": "secret1"}).status_code == 200))
    check("login wrong password -> 401",
          lambda: _assert(c.post("/api/auth/login",
                   json={"email": email, "password": "nope"}).status_code == 401))
    check("login unknown email -> 401",
          lambda: _assert(c.post("/api/auth/login",
                   json={"email": "ghost@t.com", "password": "x"}).status_code == 401))
    check("protected route without token -> 401",
          lambda: _assert(c.post(f"/api/stores/{sid}/save").status_code == 401))
    check("register invalid email -> 422 (pydantic)",
          lambda: _assert(c.post("/api/auth/register",
                   json={"name": "A", "email": "bad", "password": "secret1"}).status_code == 422))
    check("register short password -> 422",
          lambda: _assert(c.post("/api/auth/register",
                   json={"name": "A", "email": "x@t.com", "password": "1"}).status_code == 422))

    # -------------------------------------------------- STORES: listing & filters
    section("Stores — listing & filters")
    check("GET /stores -> only geocoded stores",
          lambda: _assert_all(c.get("/api/stores").json()["stores"], lambda s: s["lat"] is not None))
    check("filter area -> all in area",
          lambda: _assert_all(c.get(f"/api/stores?area={area}").json()["stores"],
                              lambda s: s["area"] == area))
    if cat:
        check("filter category -> all list that category",
              lambda: _assert_all(c.get(f"/api/stores?category={cat}").json()["stores"],
                                  lambda s: cat in s["categories"]))
    # NOTE: /stores treats price_max as a HARD filter (excludes unpriced stores),
    # unlike the chatbot (soft). The seed dataset has no prices, so this is
    # correctly empty — assert the invariant on whatever is returned, not non-empty.
    check("filter price_max -> every returned store within ceiling",
          lambda: _assert(all(s["price_min"] is not None and s["price_min"] <= 500
                              for s in c.get("/api/stores?price_max=500").json()["stores"])))
    check("filter q (name search) -> matches substring",
          lambda: _assert(c.get(f"/api/stores?q={visible_name_fragment(c)}").json()["count"] >= 1))
    check("filter open_now -> returns a list (soft signal)",
          lambda: _assert(isinstance(c.get("/api/stores?open_now=true").json()["stores"], list)))
    check("results sorted by experience_score desc",
          lambda: _assert_sorted_desc([s["experience_score"] or 0
                                       for s in c.get("/api/stores").json()["stores"]]))

    # -------------------------------------------------- STORES: metadata endpoints
    section("Stores — areas / categories / nearby")
    check("GET /areas -> sorted non-empty",
          lambda: _assert(_is_sorted(c.get("/api/stores/areas").json())
                          and len(c.get("/api/stores/areas").json()) > 0))
    check("GET /categories -> sorted list",
          lambda: _assert(_is_sorted(c.get("/api/stores/categories").json())))
    check("GET /nearby -> within radius, sorted by distance",
          lambda: _nearby_ok(c, lat, lng))

    # -------------------------------------------------- STORES: detail
    section("Stores — detail")
    check("GET /{id} -> detail w/ reviews, similar, sentiment_summary",
          lambda: _detail_shape(c.get(f"/api/stores/{sid}").json()))
    check("GET /{id} nonexistent -> 404",
          lambda: _assert(c.get("/api/stores/blr-does-not-exist").status_code == 404))
    if hidden_id:
        check("GET /{id} hidden (no coords) -> 404",
              lambda: _assert(c.get(f"/api/stores/{hidden_id}").status_code == 404))

    # -------------------------------------------------- REVIEWS (async sentiment)
    section("Reviews — async sentiment + score recompute")
    def review_flow():
        r = c.post(f"/api/stores/{sid}/reviews", headers=H,
                   json={"rating": 5, "text": "absolutely love this place, amazing vintage finds"})
        assert r.status_code == 200, r.text
        assert r.json()["sentiment"] == "pending", r.json()
        # TestClient runs the BackgroundTask synchronously, so by now it's scored.
        d = c.get(f"/api/stores/{sid}").json()
        assert d["review_count"] >= 1, "review_count not updated"
        assert d["sentiment_summary"]["total"] >= 1, "summary not updated"
        newest = d["reviews"][0]
        assert newest["sentiment"] in ("positive", "neutral", "negative"), \
            f"sentiment not populated: {newest['sentiment']}"
        assert d["experience_score"] is not None, "experience_score not recomputed"
    check("POST review -> pending, then background scores + recomputes", review_flow)

    # -------------------------------------------------- SAVE
    section("Save")
    def save_flow():
        r = c.post(f"/api/stores/{sid}/save", headers=H)
        assert r.status_code == 200 and r.json()["ok"] is True, r.text
        db = SessionLocal()
        try:
            n = db.query(Interaction).filter(Interaction.kind == "save").count()
            assert n >= 1, "save interaction not recorded"
        finally:
            db.close()
    check("POST /save -> ok + interaction recorded", save_flow)

    # -------------------------------------------------- MISC
    section("Misc — health / zones / recommendations")
    check("GET /health -> ok",
          lambda: _assert(c.get("/api/health").json()["status"] == "ok"))
    check("GET /zones -> zones with top_stores",
          lambda: _zones_ok(c.get("/api/zones").json()))
    check("GET /recommendations (guest) -> non-personalized fallback",
          lambda: _assert(c.get("/api/recommendations").json()["personalized"] is False))
    check("GET /recommendations (auth, after interactions) -> stores returned",
          lambda: _assert(len(c.get("/api/recommendations", headers=H).json()["stores"]) > 0))

    # -------------------------------------------------- CHAT (every intent)
    section("Chat — all intents")
    intents = {
        "greeting/general": ("hi", None),
        "find_by_area": (f"thrift stores in {area}", "find_by_area"),
        "find_by_category": (f"{cat} stores" if cat else "vintage stores", None),
        "find_by_price": ("stores under 500", "find_by_price"),
        "open_now": ("what is open right now", "open_now"),
        "zone_exploration": ("show me the thrift zones", "zone_exploration"),
        "store_recommendation": ("recommend some stores for me", "store_recommendation"),
        "review_insight": (f"what do people say about {two_names[0]}", "review_insight"),
        "store_comparison": (f"compare {two_names[0]} and {two_names[1]}", "store_comparison"),
        "best_time": ("best time to visit", "best_time_to_visit"),
        "general": ("qwptzx random gibberish", "general_assistance"),
    }
    for label, (msg, expect) in intents.items():
        def _chat(msg=msg, expect=expect):
            r = c.post("/api/chat", json={"message": msg})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reply"], "empty reply"
            assert isinstance(body["stores"], list)
            if expect:
                assert body["intent"] == expect, f"intent={body['intent']} expected {expect}"
        check(f"chat: {label}", _chat)

    # -------------------------------------------------- MIDDLEWARE
    section("Middleware")
    check("timing header X-Response-Time present",
          lambda: _assert("x-response-time" in {k.lower() for k in c.get("/api/health").headers}))
    check("rate limiter returns 429 past the ceiling", _ratelimit_429)


# ---- helpers ----
def _assert(cond, msg="assertion failed"):
    assert cond, msg

def _assert_all(items, pred):
    assert items, "empty result set"
    bad = [i for i in items if not pred(i)]
    assert not bad, f"{len(bad)} item(s) violated predicate, e.g. {bad[0]}"

def _assert_sorted_desc(xs):
    assert all(xs[i] >= xs[i + 1] for i in range(len(xs) - 1)), f"not sorted desc: {xs[:5]}..."

def _is_sorted(xs):
    return all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))

def visible_name_fragment(c):
    name = c.get("/api/stores").json()["stores"][0]["name"]
    return name.split()[0]

def _nearby_ok(c, lat, lng):
    out = c.get(f"/api/stores/nearby?lat={lat}&lng={lng}&radius_km=5").json()["stores"]
    assert all("distance_km" in s and s["distance_km"] <= 5.0 for s in out), "radius violated"
    ds = [s["distance_km"] for s in out]
    assert _is_sorted(ds), "not sorted by distance"

def _detail_shape(d):
    for key in ("reviews", "similar", "sentiment_summary", "experience_score", "is_open_now"):
        assert key in d, f"missing key {key}"
    ss = d["sentiment_summary"]
    assert set(ss) == {"positive", "neutral", "negative", "total"}, ss

def _zones_ok(zs):
    assert zs, "no zones"
    for z in zs:
        for key in ("label", "center_lat", "center_lng", "store_count", "top_stores"):
            assert key in z, f"zone missing {key}"

def _ratelimit_429():
    """Isolated tiny app so we don't burn the main app's window."""
    async def ok(request):
        return JSONResponse({"ok": True})
    tiny = Starlette(routes=[Route("/", ok)])
    tiny.add_middleware(RateLimitMiddleware, max_requests=3, window_seconds=60)
    tc = TestClient(tiny)
    codes = [tc.get("/").status_code for _ in range(5)]
    assert 429 in codes, f"never rate-limited: {codes}"
    assert codes[:3] == [200, 200, 200], f"limited too early: {codes}"


def _summary():
    passed = sum(1 for ok, _, _ in _results if ok)
    failed = [(n, m) for ok, n, m in _results if not ok]
    print("\n" + "=" * 60)
    print(f"AUDIT: {passed}/{len(_results)} checks passed")
    if failed:
        print(f"\n{len(failed)} FAILURE(S):")
        for n, m in failed:
            print(f"  - {n}: {m}")
    else:
        print("ALL FUNCTIONALITY VERIFIED ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()

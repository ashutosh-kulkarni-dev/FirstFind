"""Temporary verification harness (SQLite) — not shipped.

Seeds a throwaway SQLite DB and smoke-tests the app end to end so each
architecture change can be checked without a running MySQL. Sentiment goes
through the HF Inference API if HUGGINGFACE_TOKEN is set, else VADER.
Run: python _verify.py
"""
import os
import pathlib

# Force a throwaway SQLite DB BEFORE importing the app, so config picks it up.
_DB = pathlib.Path(__file__).parent / "_verify.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_DB.as_posix()}"
os.environ["FIRSTFIND_JWT_SECRET"] = "verify-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


def main():
    ok = 0
    # Seeding is now an explicit step (no longer done in lifespan).
    seed()
    with TestClient(app) as c:  # triggers lifespan (fit + warmup only)
        r = c.get("/api/health"); assert r.status_code == 200, r.text; ok += 1
        print("health:", r.json())

        r = c.get("/api/stores"); assert r.status_code == 200, r.text
        stores = r.json()["stores"]; assert stores, "no stores seeded"; ok += 1
        sid = stores[0]["id"]
        print(f"stores: {len(stores)} listed; first={sid}")

        # ---- Geocoding: fallback stores hidden from users, kept in backend ----
        from app.database import SessionLocal as _SL0
        from app.models import Store as _S0
        _db0 = _SL0()
        try:
            total = _db0.query(_S0).count()
            hidden = _db0.query(_S0).filter(_S0.lat.is_(None)).all()
            n_hidden = len(hidden)
            hidden_id = hidden[0].id if hidden else None
        finally:
            _db0.close()
        visible_ids = {s["id"] for s in stores}
        # every listed store has coordinates; no hidden store leaks into the list
        assert all(s.get("lat") is not None for s in stores), "a listed store has no coords"
        assert len(stores) == total - n_hidden, \
            f"listed {len(stores)} != visible {total - n_hidden}"
        assert hidden_id not in visible_ids, "hidden store appeared in listing"
        ok += 1
        print(f"visibility: {total} in DB, {len(stores)} visible, {n_hidden} hidden (kept in backend)")

        # a hidden store is 404 to users but still present in the DB
        r = c.get(f"/api/stores/{hidden_id}")
        assert r.status_code == 404, f"hidden store {hidden_id} not hidden: {r.status_code}"
        ok += 1
        print(f"hidden store {hidden_id}: detail -> 404 (present in DB, absent from view)")

        r = c.get(f"/api/stores/{sid}"); assert r.status_code == 200, r.text; ok += 1
        d = r.json()
        print(f"store_detail: {len(d['reviews'])} reviews, "
              f"{len(d['similar'])} similar, summary={d['sentiment_summary']}")

        r = c.get("/api/zones"); assert r.status_code == 200, r.text; ok += 1
        print(f"zones: {len(r.json())}")

        # auth + interaction + personalized recs
        import uuid
        email = f"verify-{uuid.uuid4().hex[:8]}@thriftverify.com"
        r = c.post("/api/auth/register",
                   json={"name": "Verify User", "email": email, "password": "secret1"})
        assert r.status_code == 200, r.text; ok += 1
        tok = r.json()["token"]; H = {"Authorization": f"Bearer {tok}"}

        # view a few stores + save one
        for s in stores[:3]:
            c.get(f"/api/stores/{s['id']}", headers=H)
        r = c.post(f"/api/stores/{sid}/save", headers=H); assert r.status_code == 200, r.text; ok += 1

        # Issue #4: hammer one store with repeated views -> at most ONE view row.
        for _ in range(10):
            c.get(f"/api/stores/{sid}", headers=H)
        from app.database import SessionLocal as _SL
        from app.models import Interaction as _I, User as _U
        _db = _SL()
        try:
            uid = _db.query(_U).filter(_U.email == email).first().id
            n_views = (_db.query(_I).filter(_I.user_id == uid, _I.store_id == sid,
                                            _I.kind == "view").count())
        finally:
            _db.close()
        assert n_views == 1, f"expected 1 deduped view, got {n_views}"; ok += 1
        print(f"view dedup: 11 GETs of {sid} -> {n_views} view row(s)")

        r = c.post(f"/api/stores/{sid}/reviews", headers=H,
                   json={"rating": 5, "text": "mast collection, paisa vasool"})
        assert r.status_code == 200, r.text; ok += 1
        print("review add:", r.json())

        r = c.get("/api/recommendations", headers=H); assert r.status_code == 200, r.text; ok += 1
        rec = r.json(); print(f"recommendations: personalized={rec['personalized']}, "
                              f"{len(rec['stores'])} stores")

        r = c.post("/api/chat", json={"message": "vintage stores in Koramangala under 500"})
        assert r.status_code == 200, r.text; ok += 1
        print("chat intent:", r.json()["intent"], "| stores:", len(r.json()["stores"]))

        # ---- Retrieval: area is a HARD filter (via HTTP) ----
        # Pick an area that round-trips through NL extraction (so the message
        # unambiguously resolves to it), then assert zero out-of-area leakage.
        from app.database import SessionLocal as _SLa
        from app.ml import chatbot as _cb0
        _dba = _SLa()
        try:
            vis_areas = _cb0._known_areas(_dba)
            target_area = next(
                (a for a in vis_areas
                 if _cb0._extract_area(_cb0._normalize(f"thrift stores in {a}"), vis_areas) == a
                 and _cb0._rank(_dba, area=a)),
                None)
        finally:
            _dba.close()
        assert target_area, "no round-tripping area with stores found"
        r = c.post("/api/chat", json={"message": f"thrift stores in {target_area}"})
        body = r.json(); assert r.status_code == 200, r.text
        assert body["intent"] == "find_by_area", body["intent"]
        assert body["stores"], f"no stores for {target_area}"
        assert all(s["area"] == target_area for s in body["stores"]), \
            f"AREA LEAK: {sorted({s['area'] for s in body['stores']})}"
        ok += 1
        print(f"area hard-filter: '{target_area}' -> {len(body['stores'])} stores, all in-area")

    # batch pipeline
    from app.ml.pipeline import run_pipeline
    summary = run_pipeline()
    print("pipeline:", summary); ok += 1

    # ---- Issue #1: recommender output is persisted + served from DB ----
    from app.database import SessionLocal
    from app.models import StoreSimilarity, UserRecommendation
    from app.ml.recommender import recommender, similar_ids, user_recs
    db = SessionLocal()
    try:
        n_sim = db.query(StoreSimilarity).count()
        n_rec = db.query(UserRecommendation).count()
        assert n_sim > 0, "no StoreSimilarity rows persisted"
        assert n_rec > 0, "no UserRecommendation rows persisted"; ok += 1
        print(f"persisted: {n_sim} similarity rows, {n_rec} rec rows")

        # Simulate a *fresh worker / restart*: wipe in-memory model, prove
        # serving still works purely from the DB (the point of the fix).
        recommender.sim = None
        recommender.user_vectors = {}
        some_user = db.query(UserRecommendation.user_id).first()[0]
        sim_from_db = similar_ids(db, sid)
        rec_from_db = user_recs(db, some_user)
        assert sim_from_db, "similar_ids empty with cold in-memory model"
        assert rec_from_db, "user_recs empty with cold in-memory model"; ok += 1
        print(f"cold-memory serving OK: similar={len(sim_from_db)}, recs(user {some_user})={len(rec_from_db)}")
    finally:
        db.close()

    # ---- Retrieval internals: hard-filter-then-rank, open-soft, typos, context ----
    from app.database import SessionLocal as _SLb
    from app.models import Store as _Sb
    from sqlalchemy import func as _f2
    from app.ml import chatbot as cb
    _db = _SLb()
    try:
        areas = cb._known_areas(_db)
        ta = (_db.query(_Sb.area).filter(_Sb.lat.isnot(None))
              .group_by(_Sb.area).order_by(_f2.count().desc()).first()[0])

        # area is a hard filter; bogus area yields nothing (no substitution)
        got = cb._rank(_db, area=ta, limit=100)
        assert got and all(s.area == ta for s in got), "area filter leaked"
        assert cb._rank(_db, area="__no_such_area__") == [], "empty set was substituted"
        ok += 1
        print(f"hard-filter: area={ta!r} -> {len(got)} in-area; bogus area -> 0 (no leak)")

        # open-now is SOFT: it reorders but never shrinks the eligible set
        base = cb._rank(_db, area=ta, limit=100)
        opened = cb._rank(_db, area=ta, open_now=True, limit=100)
        assert len(opened) == len(base), "open_now dropped stores (must be soft)"
        ok += 1
        print(f"open-now soft: area={ta} set size {len(base)} unchanged with open_now ranking")

        # typo / paraphrase tolerance (token-free)
        assert cb._detect_intent(cb._normalize("recomend some shops"), areas) == "store_recommendation"
        assert cb._detect_intent(cb._normalize("wat shops r opn now"), areas) == "open_now"
        if "Koramangala" in areas:
            assert cb._extract_area(cb._normalize("shops in koramanagla"), areas) == "Koramangala"
        ok += 1
        print("typo tolerance: 'recomend'->recommend, 'opn now'->open_now, 'koramanagla'->Koramangala")

        # multi-word area misspelling resolves (adjacent-char swap in first token)
        multi = next((a for a in areas if len(a.split()) >= 2 and len(a.split()[0]) >= 5), None)
        if multi:
            w = multi.split()[0]
            typo_first = w[:2] + w[3] + w[2] + w[4:]        # swap chars 3 & 4
            typo = multi.replace(w, typo_first, 1)
            got = cb._extract_area(cb._normalize(f"thrift shops in {typo}"), areas)
            assert got == multi, f"multi-word typo '{typo}' -> {got!r}, expected {multi!r}"
            ok += 1
            print(f"multi-word area typo: '{typo}' -> '{multi}'")

        # ---- Soft barriers: price & category exclude ONLY known violations ----
        vis = _db.query(_Sb).filter(_Sb.lat.isnot(None)).limit(3).all()
        a_s, b_s, c_s = vis[0], vis[1], vis[2]
        common = a_s.area
        b_s.area = c_s.area = common                        # neutralise the area filter
        a_s.price_min, a_s.price_max = 200, 400             # cheap        -> keep
        b_s.price_min, b_s.price_max = 900, 1500            # over budget  -> exclude
        c_s.price_min = c_s.price_max = None                # unknown      -> keep
        _db.flush()
        ids = {s.id for s in cb._rank(_db, area=common, price_max=500, limit=100)}
        assert a_s.id in ids, "cheap store wrongly excluded"
        assert c_s.id in ids, "unknown-price store excluded (must be soft-included)"
        assert b_s.id not in ids, "over-budget store included (must be excluded)"
        ok += 1
        print("price soft: cheap + unknown-price included, over-budget excluded")

        a_s.categories, b_s.categories, c_s.categories = "vintage,denim", "formal", ""
        b_s.price_min = None                                # clear price so only category decides
        _db.flush()
        ids = {s.id for s in cb._rank(_db, area=common, category="vintage", limit=100)}
        assert a_s.id in ids, "known-match category excluded"
        assert c_s.id in ids, "unknown-category store excluded (must be soft-included)"
        assert b_s.id not in ids, "known-mismatch category included (must be excluded)"
        ok += 1
        print("category soft: match + unknown-category included, known-mismatch excluded")
        _db.rollback()   # discard the mutations used for the soft-barrier checks

        # rich context payload on the reviewed store
        st = _db.get(_Sb, sid)
        ctx = cb._build_context(_db, [st], "review_insight")[0]
        assert {"name", "area", "is_open_now"} <= set(ctx), ctx
        assert "sentiment_summary" in ctx and ctx["review_count"] >= 1, ctx
        ok += 1
        print(f"context richness: {len(ctx)} fields incl sentiment_summary={ctx['sentiment_summary']}")
    finally:
        _db.close()

    print(f"\nALL {ok} CHECKS PASSED")


if __name__ == "__main__":
    main()

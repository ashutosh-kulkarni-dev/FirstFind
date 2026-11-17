"""Recommender: similarity features, signals, reasons, chain variety, and the
top-rated ordering. These check that it behaves sensibly — there is no
interaction data yet to measure how accurate it is."""
import uuid
from types import SimpleNamespace

import numpy as np

from app.ml.recommender import Recommender, chain_key, match_pct, price_tier
from app.models import Interaction, Store, UserRecommendation


def S(id, name=None, kind="thrift", tags="", cats="", lat=12.97, lng=77.60,
      pmin=None, pmax=None, est=False):
    return SimpleNamespace(id=id, name=name or id, store_type=kind, tags=tags, categories=cats,
                           lat=lat, lng=lng, price_min=pmin, price_max=pmax,
                           price_estimated=est, experience_score=None)


def fit(stores, interactions=()):
    r = Recommender()
    r.fit(list(interactions), [s.id for s in stores], stores)
    return r


def test_chain_key_and_price_tier():
    assert chain_key("Fabindia, HSR Layout") == chain_key("FABINDIA - JP Nagar") == "fabindia"
    assert chain_key("Rare Rabbit | Indiranagar") == "rare rabbit"
    assert price_tier(S("a", pmin=200, pmax=600)) == 0
    assert price_tier(S("a", pmin=800, pmax=1500)) == 1
    assert price_tier(S("a", pmin=1500, pmax=4000)) == 2
    assert price_tier(S("a", pmin=300, pmax=1500, est=True)) is None   # generic estimate
    assert price_tier(S("a")) is None


def test_similarity_follows_kind_tags_and_distance():
    stores = [
        S("a", tags="womenswear,ethnic"),
        S("near_same", tags="womenswear,ethnic", lat=12.975),          # ~0.6 km, same style
        S("far_same", tags="womenswear,ethnic", lat=13.07),            # ~11 km, same style
        S("near_other", kind="branded", tags="menswear", lat=12.972),  # close, different
    ]
    r = fit(stores)
    i = r._idx
    sim = r.sim[i["a"]]
    assert sim[i["near_same"]] > sim[i["far_same"]] > sim[i["near_other"]]
    ranked = r.similar_ranked(i["a"], 3)
    assert [r.store_ids[j] for j, _, _ in ranked][0] == "near_same"
    assert ranked[0][2].startswith("Similar style, ") and "m away" in ranked[0][2]
    # Sharing only the store kind is not "Similar style".
    near_other_kind = S("b", tags="menswear", lat=12.971)
    r2 = fit([S("a", tags="womenswear"), near_other_kind])
    assert r2.similar_ranked(0, 1)[0][2].startswith("Also a thrift store, ")
    # Not capped at 40% any more: a close twin is a strong match.
    assert match_pct(ranked[0][1]) >= 80
    assert match_pct(0.3) is None


def test_similar_leaves_out_own_chain_and_repeats():
    stores = [S("x1", "Fabindia, HSR Layout", kind="branded", tags="ethnic"),
              S("x2", "Fabindia, JP Nagar", kind="branded", tags="ethnic", lat=12.971),
              S("y1", "Westside - Koramangala", kind="branded", tags="ethnic", lat=12.972),
              S("y2", "Westside - BTM", kind="branded", tags="ethnic", lat=12.973),
              S("z", "Some Boutique", kind="branded", tags="ethnic", lat=12.974)]
    r = fit(stores)
    ids = [r.store_ids[j] for j, _, _ in r.similar_ranked(r._idx["x1"], 4)]
    assert "x2" not in ids                      # another branch of the same chain
    assert sum(i.startswith("y") for i in ids) == 1   # one Westside, not two
    assert "z" in ids


def test_user_picks_use_strong_signals_and_explain_them():
    stores = [S("liked", tags="womenswear"), S("viewed", kind="branded", tags="menswear", lat=13.05),
              S("like_twin", tags="womenswear", lat=12.971),
              S("view_twin", kind="branded", tags="menswear", lat=13.051)]
    r = fit(stores, [(1, "liked", "like"), (1, "viewed", "view")])
    picks = r.user_ranked(1, 2)
    ids = [r.store_ids[j] for j, _, _ in picks]
    assert ids[0] == "like_twin"                # the liked store outweighs the viewed one
    assert picks[0][2] == "Because you rated liked highly"
    assert "liked" not in ids and "viewed" not in ids   # never re-recommends what you know
    r2 = fit(stores, [(1, "liked", "save")])
    assert r2.user_ranked(1, 1)[0][2] == "Because you saved liked"


def test_chains_are_recognised_by_brand_and_first_word():
    from app.ml.recommender import chain_keys
    keys = chain_keys(["Pantaloons (Indiranagar)", "Pantaloons south zonal office",
                       "Fabindia Experience Center, MG Road", "Fabindia, HSR Layout",
                       "Zudio", "Zudio Koramangala", "Thrift Hands", "Thrift", "EcoDhaga"])
    assert keys[0] == keys[1] == "pantaloons"
    assert keys[2] == keys[3] == "fabindia"
    assert keys[4] == keys[5] == "zudio"
    assert keys[6] is None and keys[7] is None   # "thrift" is too common to mean a chain
    assert keys[8] is None                       # only one branch


def test_picks_alternate_between_the_stores_behind_them():
    liked = [S("liked", tags="ethnic")] + [S(f"e{i}", tags="ethnic", lat=12.97 + i / 1000) for i in range(6)]
    saved = [S("saved", kind="branded", tags="denim", lat=13.05)] +             [S(f"d{i}", kind="branded", tags="denim", lat=13.05 + i / 1000) for i in range(6)]
    r = fit(liked + saved, [(1, "liked", "like"), (1, "saved", "save")])
    reasons = [reason for _, _, reason in r.user_ranked(1, 4)]
    assert reasons.count("Because you rated liked highly") == 2
    assert reasons.count("Because you saved saved") == 2


def test_cf_only_counts_with_enough_users():
    stores = [S("a", tags="womenswear"), S("b", kind="branded", tags="menswear", lat=13.05)]
    few = fit(stores, [(1, "a", "save"), (1, "b", "save")])
    assert not few.cf_used.any()
    many = fit(stores, [(u, sid, "save") for u in range(1, 4) for sid in ("a", "b")])
    assert many.cf_used[0, 1]
    assert many.sim[0, 1] > few.sim[0, 1]
    assert many.similar_ranked(0, 1)[0][2].startswith("People who liked this also liked it")


# ---------------------------------------------------------------- API level

def _user(client):
    r = client.post("/api/auth/register", json={"name": "T", "email": f"u{uuid.uuid4().hex[:8]}@example.com",
                                                "password": "secret12"})
    body = r.json()
    return body["id"], {"Authorization": f"Bearer {body['token']}"}


def _stores(db):
    db.add_all([Store(id="blr-0001", name="EcoDhaga", area="Koramangala", lat=12.935, lng=77.624,
                      tags="womenswear", experience_score=None, google_rating=4.8),
                Store(id="blr-0002", name="Love Me Twice", area="Indiranagar", lat=12.973, lng=77.640,
                      tags="womenswear", experience_score=4.2),
                Store(id="blr-0003", name="Thrft", area="Kothanur", lat=12.870, lng=77.582,
                      experience_score=4.6)])
    db.commit()


def test_top_rated_puts_unscored_stores_last(client, db):
    _stores(db)
    ids = [s["id"] for s in client.get("/api/recommendations").json()["stores"]]
    assert ids == ["blr-0003", "blr-0002", "blr-0001"]


def test_review_and_list_record_signals_once(client, db):
    _stores(db)
    uid, auth = _user(client)
    client.post("/api/stores/blr-0001/reviews", headers=auth, json={"rating": 5, "text": "Lovely"})
    client.post("/api/stores/blr-0002/reviews", headers=auth, json={"rating": 2, "text": "Meh"})
    client.post("/api/stores/blr-0003/save", headers=auth)
    client.post("/api/stores/blr-0003/save", headers=auth)   # a repeat changes nothing
    client.post("/api/lists", headers=auth, json={"name": "Run", "store_ids": ["blr-0002"]})
    kinds = sorted((i.store_id, i.kind) for i in db.query(Interaction).filter_by(user_id=uid))
    assert kinds == [("blr-0001", "like"), ("blr-0002", "save"), ("blr-0003", "save")]


def test_store_page_and_picks_carry_reasons(client, db):
    from app.ml.tasks import build_recommender
    _stores(db)
    uid, auth = _user(client)
    db.add(Interaction(user_id=uid, store_id="blr-0001", kind="save"))
    db.commit()
    build_recommender()
    similar = client.get("/api/stores/blr-0001").json()["similar"]
    assert similar and all(s["reason"] for s in similar)
    assert similar[0]["id"] == "blr-0002"        # same tags, nearer than Thrft
    db.expire_all()
    assert db.query(UserRecommendation).filter_by(user_id=uid).count() > 0
    picks = client.get("/api/recommendations", headers=auth).json()
    assert picks["personalized"] is True
    assert picks["stores"][0]["reason"] == "Because you saved EcoDhaga"


def test_attribute_matrix_ignores_estimated_prices():
    a = S("a", kind="thrift", pmin=300, pmax=1500, est=True)
    b = S("b", kind="thrift", pmin=300, pmax=1500, est=True)
    X = Recommender()._attribute_matrix([a, b])
    assert np.count_nonzero(X[0]) == 1          # only the kind, no price tier

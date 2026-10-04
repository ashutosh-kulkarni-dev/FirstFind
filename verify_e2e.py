"""End-to-end backend review flow verification."""
import time, sys
sys.path.insert(0, "c:/Users/Ashutosh Kulkarni/ThriftFind/app/backend")

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import Review as RM, Store, User

client = TestClient(app, raise_server_exceptions=True)
STORE_ID = "blr-0001"
EMAIL    = "e2e_final@example.com"
PASSWORD = "TestFlow99!"

# ── Baseline ─────────────────────────────────────────────────────────────
db = SessionLocal()
s = db.get(Store, STORE_ID)
score_before, count_before = s.experience_score, s.review_count
print(f"[0] BASELINE  {s.name}: score={score_before}  review_count={count_before}")

existing = db.query(User).filter(User.email == EMAIL).first()
if existing:
    db.query(RM).filter(RM.user_id == existing.id).delete()
    db.delete(existing)
    db.commit()
    print("   (cleaned up previous e2e user)")
db.close()

# ── Register ─────────────────────────────────────────────────────────────
r = client.post("/api/auth/register",
    json={"email": EMAIL, "password": PASSWORD, "name": "E2E Tester"})
assert r.status_code == 200, f"Register {r.status_code}: {r.text}"
token  = r.json()["token"]
user_id = r.json()["id"]
print(f"[1] Register 200  user_id={user_id}")

# ── /me round-trip ───────────────────────────────────────────────────────
r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
assert r.status_code == 200
print(f'[2] GET /me: 200  name={r.json()["name"]!r}')

# ── POST review ──────────────────────────────────────────────────────────
review_text = "Amazing! Paisa vasool, bakwaas nahi. Sustainable fashion at its best."
r = client.post(f"/api/stores/{STORE_ID}/reviews",
    json={"rating": 5, "text": review_text},
    headers={"Authorization": f"Bearer {token}"})
assert r.status_code == 200, f"Review POST {r.status_code}: {r.text}"
print(f"[3] POST review 200  response={r.json()}")

# ── Find review in DB ─────────────────────────────────────────────────────
db = SessionLocal()
rev = db.query(RM).filter(RM.user_id == user_id, RM.store_id == STORE_ID).first()
rid  = rev.id if rev else None
snippet = rev.text[:40] if rev else None
print(f"[3b] In DB: id={rid}  text={snippet!r}")
assert rid, "Review not found in DB after POST"

# ── Wait for background HF sentiment ─────────────────────────────────────
print("[4] Waiting for HF xlm-roberta background task...")
for i in range(20):
    db.expire_all()
    rev = db.get(RM, rid)
    if rev and rev.sentiment:
        break
    time.sleep(0.5)
sentiment   = rev.sentiment      if rev else None
sent_score  = rev.sentiment_score if rev else None
print(f"[4] HF xlm-roberta: sentiment={sentiment!r}  compound={sent_score}")
assert sentiment, "Background sentiment task never completed!"

# ── Store score updated ──────────────────────────────────────────────────
db.expire_all()
s2 = db.get(Store, STORE_ID)
score_after, count_after = s2.experience_score, s2.review_count
print(f"[5] experience_score: {score_before} -> {score_after}")
print(f"    review_count:      {count_before} -> {count_after}")
assert count_after == count_before + 1, f"review_count not incremented: {count_before}->{count_after}"
db.close()

# ── GET /stores/:id returns new review ───────────────────────────────────
r = client.get(f"/api/stores/{STORE_ID}")
d = r.json()
new_rev = next((rv for rv in d.get("reviews", []) if rv.get("id") == rid), None)
print(f'[6] GET /stores/{STORE_ID}: {len(d.get("reviews", []))} reviews in response')
if new_rev:
    print(f'    Review: user_name={new_rev["user_name"]!r}  rating={new_rev["rating"]}  sentiment={new_rev["sentiment"]!r}')
assert new_rev, "New review not returned by GET /stores/:id"

print()
print("=" * 60)
print("VERDICT: ALL BACKEND CHECKS PASS")
print("=" * 60)
print(f"  Auth (register + /me):       OK")
print(f"  Review saved:                OK  id={rid}")
print(f"  HF xlm-roberta scored:       OK  {sentiment!r}  compound={sent_score:.4f}")
print(f"  review_count incremented:    {count_before} -> {count_after}  OK")
print(f"  experience_score:            {score_before} -> {score_after}")
print(f"  Review in GET /stores:       OK  user={new_rev['user_name']!r}")

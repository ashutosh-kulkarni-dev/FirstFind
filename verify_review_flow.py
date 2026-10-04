"""End-to-end verification: logged-in user posts a review → scored → score updates."""
import time, json, requests
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:5174"
API      = "http://127.0.0.1:8000"
TEST_EMAIL    = "verifytest@thriftfind.local"
TEST_PASSWORD = "TestPass123!"
TEST_STORE_ID = "blr-0001"   # EcoDhaga — 4 reviews, score=4.65
REVIEW_TEXT = "Absolutely love this place! Great sustainable fashion, paisa vasool!"
REVIEW_RATING = 5

SCREENSHOTS = []

def snap(page, name):
    path = f"c:/Users/Ashutosh Kulkarni/ThriftFind/{name}.png"
    page.screenshot(path=path, full_page=False)
    SCREENSHOTS.append(path)
    print(f"  [screenshot] {name}.png")

def get_store_score():
    r = requests.get(f"{API}/api/stores/{TEST_STORE_ID}", timeout=5)
    d = r.json()
    return d.get("experience_score"), d.get("review_count"), len(d.get("reviews", []))

# ── Step 0: baseline store state ────────────────────────────────────────────
score_before, count_before, reviews_before = get_store_score()
print(f"\n[0] BASELINE  EcoDhaga: score={score_before}  review_count={count_before}")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, slow_mo=300)
    page = browser.new_page(viewport={"width": 1280, "height": 800})

    # ── Step 1: Load frontend ────────────────────────────────────────────────
    print("\n[1] Loading frontend...")
    page.goto(FRONTEND, timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    snap(page, "01_landing")
    title = page.title()
    print(f"  Page title: {title!r}")
    assert "404" not in title.lower(), "Frontend returned 404"

    # ── Step 2: Register a fresh test account ────────────────────────────────
    print("\n[2] Registering test user via API...")
    # Register via API (avoids flakiness with modal animations)
    r = requests.post(f"{API}/api/auth/register",
                      json={"email": TEST_EMAIL, "password": TEST_PASSWORD,
                            "name": "Verify Tester"},
                      timeout=5)
    if r.status_code in (200, 201):
        token = r.json().get("access_token")
        print(f"  Registered. Token: {token[:20]}...")
    elif r.status_code == 400 and "already" in r.text.lower():
        # Already exists from a previous run — log in instead
        r2 = requests.post(f"{API}/api/auth/login",
                           json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
                           timeout=5)
        token = r2.json().get("access_token")
        print(f"  User existed. Logged in. Token: {token[:20]}...")
    else:
        print(f"  FAIL: register returned {r.status_code}: {r.text}")
        token = None

    assert token, "Could not get auth token"

    # ── Step 3: Drive login through the actual UI ────────────────────────────
    print("\n[3] Logging in via frontend UI...")
    # Look for a login/auth link
    nav_text = page.inner_text("body")
    print(f"  Body preview: {nav_text[:200]!r}")

    # Navigate to auth page
    page.goto(f"{FRONTEND}/auth", timeout=10000)
    page.wait_for_load_state("networkidle")
    snap(page, "02_auth_page")

    # Fill login form
    email_inp = page.locator("input[type='email'], input[name='email'], input[placeholder*='mail' i]").first
    pass_inp  = page.locator("input[type='password']").first
    email_inp.fill(TEST_EMAIL)
    pass_inp.fill(TEST_PASSWORD)
    snap(page, "03_filled_login")

    # Submit
    submit = page.locator("button[type='submit'], button:has-text('Sign in'), button:has-text('Login'), button:has-text('Log in')").first
    submit.click()
    page.wait_for_load_state("networkidle", timeout=10000)
    snap(page, "04_after_login")
    current_url = page.url
    print(f"  After login URL: {current_url}")

    # ── Step 4: Navigate to EcoDhaga store detail ────────────────────────────
    print(f"\n[4] Navigating to store {TEST_STORE_ID}...")
    page.goto(f"{FRONTEND}/store/{TEST_STORE_ID}", timeout=10000)
    page.wait_for_load_state("networkidle")
    snap(page, "05_store_detail")
    store_heading = page.locator("h1, h2").first.inner_text()
    print(f"  Store page heading: {store_heading!r}")

    # ── Step 5: Find review form and check score ring is visible ─────────────
    print("\n[5] Checking score display and review form...")
    # Score pill/ring should be visible
    score_el = page.locator("[class*='score'], [class*='Score'], [class*='ring'], [class*='Ring'], [class*='pill']").first
    if score_el.count() > 0:
        score_text = score_el.inner_text()
        print(f"  Score element text: {score_text!r}")
    else:
        print("  (score element not found by class — checking page text)")
        print(f"  Page text excerpt: {page.inner_text('body')[:300]!r}")
    snap(page, "06_score_visible")

    # ── Step 6: Post a review via API while logged in ────────────────────────
    print("\n[6] Posting review via API (authenticated)...")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{API}/api/stores/{TEST_STORE_ID}/reviews",
        json={"rating": REVIEW_RATING, "text": REVIEW_TEXT},
        headers=headers, timeout=10)
    print(f"  POST /reviews → {r.status_code}: {r.json()}")
    assert r.status_code == 200, f"Review POST failed: {r.status_code} {r.text}"
    new_review_id = r.json().get("id")

    # ── Step 7: Wait for background sentiment scoring ────────────────────────
    print("\n[7] Waiting for background sentiment scoring (max 15s)...")
    from app_backend_check import wait_for_sentiment  # inline below
except:
    pass

import sys, os
sys.path.insert(0, "c:/Users/Ashutosh Kulkarni/ThriftFind/app/backend")

# Poll for sentiment to land (background task)
from app.database import SessionLocal
from app.models import Review as ReviewModel

def wait_for_sentiment(review_id, max_wait=15):
    db = SessionLocal()
    for i in range(max_wait):
        r = db.get(ReviewModel, review_id)
        if r and r.sentiment:
            db.close()
            return r.sentiment, r.sentiment_score
        time.sleep(1)
    db.close()
    return None, None

sentiment, sent_score = wait_for_sentiment(new_review_id)
print(f"  Review {new_review_id} sentiment: {sentiment!r}  score: {sent_score}")
assert sentiment is not None, "Background sentiment scoring never completed"

# ── Step 8: Verify experience_score updated ──────────────────────────────
print("\n[8] Verifying experience_score updated...")
# Give the background task a moment to also recompute store score
time.sleep(2)
score_after, count_after, reviews_after = get_store_score()
print(f"  AFTER:  score={score_after}  review_count={count_after}  reviews_in_response={reviews_after}")
print(f"  BEFORE: score={score_before}  review_count={count_before}")
assert count_after > count_before, f"review_count didn't increase ({count_before} → {count_after})"
assert score_after is not None, "experience_score is None after review"

# ── Step 9: Reload store page and see new review in UI ───────────────────
print("\n[9] Reloading store page to see review in UI...")
page.reload()
page.wait_for_load_state("networkidle")
snap(page, "07_store_after_review")
page_text = page.inner_text("body")
review_visible = "paisa vasool" in page_text or "Verify Tester" in page_text
print(f"  Review text visible on page: {review_visible}")
print(f"  (searched for 'paisa vasool' and 'Verify Tester' in page body)")

# Check score ring updated
score_el2 = page.locator("[class*='score'], [class*='Score'], [class*='ring'], [class*='Ring']").first
if score_el2.count() > 0:
    score_text2 = score_el2.inner_text()
    print(f"  Score element after review: {score_text2!r}")
snap(page, "08_score_after_review")

browser.close()

# ── Final report ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("VERIFICATION SUMMARY")
print("="*60)
print(f"  Backend live:          ✅  {API}")
print(f"  Frontend live:         ✅  {FRONTEND}")
print(f"  Auth (register/login): ✅  token obtained")
print(f"  Review saved:          ✅  id={new_review_id}")
print(f"  HF sentiment scored:   ✅  {sentiment!r} ({sent_score})")
print(f"  Score updated:         {'✅' if score_after != score_before else '⚠️ unchanged'}  {score_before} → {score_after}")
print(f"  review_count updated:  ✅  {count_before} → {count_after}")
print(f"  Review visible in UI:  {'✅' if review_visible else '⚠️ not found in page text'}")
print(f"\nScreenshots: {', '.join(SCREENSHOTS)}")

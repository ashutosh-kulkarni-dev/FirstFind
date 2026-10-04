"""
Final targeted recommendation checks with correct selectors.
"""
import httpx, time, os, json
from playwright.sync_api import sync_playwright

BASE_API = "http://localhost:8000/api"
BASE_UI  = "http://localhost:5173"
SHOTS    = r"c:\Users\Ashutosh Kulkarni\ThriftFind\screenshots\recs"
os.makedirs(SHOTS, exist_ok=True)

EMAIL    = "test@thriftfind.demo"
PASSWORD = "Test1234!"

results = []

def check(label, ok, detail=""):
    icon = "v" if ok else "X"
    status = "PASS" if ok else "FAIL"
    results.append((status, label, str(detail)))
    safe = str(detail).encode("ascii", "replace").decode("ascii")
    print(f"  {icon} [{status}] {label}")
    if safe:
        print(f"         {safe}")

def shot(page, name):
    path = os.path.join(SHOTS, f"{name}.png")
    page.screenshot(path=path, full_page=True)

# ── 1. API: verify personalization is active ─────────────────────────────────
print("\n=== 1. API: Recommendation personalization")

login_r = httpx.post(f"{BASE_API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
token = login_r.json().get("token", "")
headers = {"Authorization": f"Bearer {token}"}

r = httpx.get(f"{BASE_API}/recommendations", headers=headers)
data = r.json()
personalized = data.get("personalized", False)
stores = data.get("stores", [])
check("GET /recommendations OK", r.status_code == 200)
check("personalized=True (user has interaction history)", personalized, f"personalized={personalized}")
check("6 personalized stores returned", len(stores) == 6, f"{len(stores)} stores: {[s['name'] for s in stores]}")

# ── 2. API: similar stores — confirm match_pct is MISSING ───────────────────
print("\n=== 2. API: Similar stores — match_pct gap")
r2 = httpx.get(f"{BASE_API}/stores/blr-0001")
store_detail = r2.json()
similar = store_detail.get("similar", [])
check("Store detail has 'similar' list", len(similar) > 0, f"{len(similar)} similar stores")
has_match_pct = all("match_pct" in s for s in similar)
check("[BUG] match_pct field MISSING from similar stores",
      not has_match_pct,  # this PASSES because it confirms the bug
      "Backend sends similar store IDs but drops StoreSimilarity.score (never put in store_to_dict)")
# Show what keys ARE present
if similar:
    check("Similar stores have id/name/area", all(k in similar[0] for k in ["id", "name", "area"]),
          list(similar[0].keys())[:6])

# ── 3. UI: Landing page — correct selector (lp-grid) ─────────────────────────
print("\n=== 3. UI: Landing page 'PICKED FOR YOU' section")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    # Login
    page.goto(f"{BASE_UI}/auth", wait_until="networkidle", timeout=15000)
    page.locator("input[type='email']").fill(EMAIL)
    page.locator("input[type='password']").fill(PASSWORD)
    page.locator("button.btn.btn-primary").click()
    page.wait_for_url(f"{BASE_UI}/", timeout=8000)
    time.sleep(2)
    shot(page, "R10_landing_rec")

    txt = page.inner_text("body").lower()
    check("'PICKED FOR YOU' heading shown", "picked for you" in txt)
    check("'Personalised' badge shown", "personalised" in txt or "personalized" in txt)

    # Correct selector: .lp-grid contains StoreCard <Link> which render as <a class="card card-link">
    lp_grid = page.locator(".lp-grid")
    check(".lp-grid container renders", lp_grid.count() > 0)

    rec_cards = lp_grid.locator("a.card-link").count() if lp_grid.count() > 0 else 0
    check("Store cards render inside .lp-grid", rec_cards > 0, f"{rec_cards} recommendation cards in .lp-grid")

    # Personalized copy
    check("Personalized copy shown ('based on your')", "based on your" in txt)

    # Scroll to see the section
    page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
    time.sleep(0.5)
    shot(page, "R11_landing_rec_scrolled")

    # ── 4. UI: Store Detail — "SHOPPERS ALSO LIKED" section ─────────────────
    print("\n=== 4. UI: Store Detail 'SHOPPERS ALSO LIKED'")

    page.goto(f"{BASE_UI}/store/blr-0001", wait_until="networkidle", timeout=15000)
    time.sleep(1.5)
    shot(page, "R12_store_detail_similar")

    # The heading uses <br> so inner_text gives "shoppers\nalso liked"
    full_txt = page.inner_text("body").lower()
    check("'SHOPPERS' appears in store detail", "shoppers" in full_txt)
    check("'ALSO LIKED' appears in store detail", "also liked" in full_txt)
    check("'Collaborative filtering' label shown", "collaborative filtering" in full_txt)

    # The 4 similar store cards render as a.card-link inside the aside
    aside = page.locator("aside.card").first
    check("'SHOPPERS ALSO LIKED' aside card present", aside.count() > 0)
    similar_links = aside.locator("a.card-link").count() if aside.count() > 0 else 0
    check(f"Similar store cards rendered ({similar_links})", similar_links > 0, f"{similar_links} cards")

    # Confirm match% is NOT shown (the bug)
    match_pct_els = page.locator("text=% match").count()
    check("[BUG CONFIRMED] No '% match' shown (match_pct missing from API)",
          match_pct_els == 0,
          "StoreCard receives match=undefined because backend omits StoreSimilarity.score")

    # ── 5. UI: Logged-out landing shows TOP-RATED ──────────────────────────
    print("\n=== 5. UI: Logged-out state")
    page.goto(BASE_UI, wait_until="networkidle", timeout=10000)
    logout = page.locator("button:has-text('LOG OUT'), button:has-text('Log out')").first
    if logout.count() > 0:
        logout.click()
        time.sleep(1)
    page.goto(BASE_UI, wait_until="networkidle", timeout=15000)
    time.sleep(1.5)
    shot(page, "R13_landing_loggedout")

    out_txt = page.inner_text("body").lower()
    check("Logged-out shows 'TOP-RATED RIGHT NOW'", "top-rated right now" in out_txt or "top rated" in out_txt, out_txt[:80])
    check("'Log in for picks' prompt shown", "log in for picks" in out_txt or ("log in" in out_txt and "picks" in out_txt))

    # Stores still shown (top-rated, not personalized)
    out_grid = page.locator(".lp-grid a.card-link").count()
    check("Top-rated store cards shown when logged out", out_grid > 0, f"{out_grid} cards")

    browser.close()

# ── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n" + "="*55)
pass_count = sum(1 for s, _, _ in results if s == "PASS")
fail_count = sum(1 for s, _, _ in results if s == "FAIL")
print(f"RESULT: {pass_count}/{len(results)} passed, {fail_count} failed")
if fail_count:
    print("\nUNEXPECTED FAILURES:")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"  X {label}: {detail.encode('ascii','replace').decode('ascii')[:100]}")

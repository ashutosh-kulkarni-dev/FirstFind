"""
Verify the full Save Lists feature for logged-in users.
"""
import httpx, time, os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_API = "http://localhost:8000/api"
BASE_UI  = "http://localhost:5173"
REPO_ROOT = Path(__file__).resolve().parents[2]
SHOTS    = str(REPO_ROOT / "screenshots" / "lists")
os.makedirs(SHOTS, exist_ok=True)

EMAIL    = "test@thriftfind.demo"
PASSWORD = "Test1234!"

# Koramangala cluster pre-seeded via deep-link (lat/lng confirmed to have 6 stores)
CLUSTER_URL = f"{BASE_UI}/explore?lat=12.9357&lng=77.6241&radius=1.5"

results = []

def check(label, ok, detail=""):
    icon = "v" if ok else "X"
    status = "PASS" if ok else "FAIL"
    results.append((status, label, str(detail)))
    safe = str(detail).encode("ascii", "replace").decode("ascii")
    print(f"  {icon} [{status}] {label}")
    if safe:
        print(f"         {safe[:150]}")
    return ok

def shot(page, name):
    page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)

# Pre-clean lists
login_r = httpx.post(f"{BASE_API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
token   = login_r.json().get("token", "")
headers = {"Authorization": f"Bearer {token}"}
existing = httpx.get(f"{BASE_API}/lists", headers=headers).json()
for lst in existing:
    httpx.delete(f"{BASE_API}/lists/{lst['id']}", headers=headers)
print(f"[setup] Cleared {len(existing)} pre-existing list(s)")

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
    print("[setup] Logged in\n")

    # ═══════════════════════════════════════════════════════════════════════
    print("=== 1. Explore sidebar 'Your lists' — empty state")
    page.goto(f"{BASE_UI}/explore", wait_until="networkidle", timeout=15000)
    time.sleep(1)
    shot(page, "L01_explore_no_lists")

    sb = page.inner_text("body").lower()
    check("'Your lists' section in sidebar", "your lists" in sb)
    check("Empty state hint shown", "no lists yet" in sb or "double-click" in sb)

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 2. Explore deep-link opens cluster (Koramangala, 1.5 km radius)")
    page.goto(CLUSTER_URL, wait_until="networkidle", timeout=15000)
    time.sleep(2)
    shot(page, "L02_cluster_preloaded")

    cl_txt = page.inner_text("body").lower()
    check("Cluster pre-loads from URL params", "save list" in cl_txt or "clear" in cl_txt, cl_txt[:120])

    save_btn = page.locator("button:has-text('+ Save list')").first
    check("'+ Save list' button visible", save_btn.count() > 0)

    # ClusterResult shows store count
    cluster_aside = page.locator(".explore-aside").first
    aside_txt = cluster_aside.inner_text().lower() if cluster_aside.count() else cl_txt
    check("Cluster shows stores in sidebar", any(c.isdigit() for c in aside_txt))
    shot(page, "L03_cluster_stores")

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 3. Click '+ Save list' -> name modal -> save -> redirect to /lists")
    if save_btn.count() > 0:
        save_btn.click()
        time.sleep(0.8)
        shot(page, "L04_modal")

        modal_input = page.locator("input.input[placeholder='My thrift run']").first
        check("Name input appears in modal", modal_input.count() > 0)

        if modal_input.count() > 0:
            modal_input.click(click_count=3)
            modal_input.fill("Koramangala Thrift Run")
            shot(page, "L05_modal_named")

            confirm = page.locator("button.btn.btn-primary:has-text('Save list')").first
            check("'Save list' confirm button in modal", confirm.count() > 0)

            cancel = page.locator("button.btn.btn-light:has-text('Cancel')").first
            check("'Cancel' button in modal", cancel.count() > 0)

            if confirm.count() > 0:
                confirm.click()
                try:
                    page.wait_for_url(f"{BASE_UI}/lists", timeout=8000)
                    check("Saving redirects to /lists", True, page.url)
                except Exception:
                    check("Saving redirects to /lists", False, f"URL: {page.url}")
                time.sleep(1)
                shot(page, "L06_lists_after_save")
    else:
        check("Save list modal skipped (button not found)", False, "investigate cluster URL")

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 4. Lists page — new list visible with store count")
    page.goto(f"{BASE_UI}/lists", wait_until="networkidle", timeout=15000)
    time.sleep(1)
    shot(page, "L07_lists")

    lp_txt = page.inner_text("body").lower()
    check("New list visible on /lists", "koramangala thrift run" in lp_txt, lp_txt[:200])

    cards = page.locator(".card")
    check("List card(s) present", cards.count() > 0, f"{cards.count()} card(s)")

    # Store count badge
    check("Store count shown on list card", "store" in lp_txt)

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 5. Expand list card -> stores appear")
    first_card = cards.first
    if first_card.count() > 0:
        first_card.click()
        time.sleep(0.8)
        shot(page, "L08_expanded")
        exp_txt = page.inner_text("body").lower()
        store_links = page.locator(".card a[href*='/store/']").count()
        check("Stores show inside expanded card", store_links > 0, f"{store_links} store links")

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 6. Rename list")
    rename_btn = page.locator("button[title='Rename']").first
    check("Rename (pencil) button present", rename_btn.count() > 0)

    if rename_btn.count() > 0:
        rename_btn.click()
        time.sleep(0.5)
        shot(page, "L09_rename")

        # The rename input is autoFocus — get the focused element
        rename_input = page.locator("input.input:focus, input.input").last
        check("Rename input visible", rename_input.count() > 0)
        if rename_input.count() > 0:
            rename_input.click(click_count=3)
            rename_input.fill("My Koramangala Picks")

            save_rename = page.locator("button.btn.btn-primary:has-text('Save')").first
            check("'Save' button for rename", save_rename.count() > 0)
            if save_rename.count() > 0:
                save_rename.click()
                time.sleep(0.8)
                shot(page, "L10_renamed")
                renamed_txt = page.inner_text("body").lower()
                check("List name updated to new name", "my koramangala picks" in renamed_txt, renamed_txt[:200])

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 7. 'Open on map' button (circle Map icon)")
    map_btn = page.locator("button[title='Open on map']").first
    check("'Open on map' (Map) button present", map_btn.count() > 0)

    if map_btn.count() > 0:
        map_btn.click()
        page.wait_for_load_state("networkidle", timeout=8000)
        time.sleep(1)
        shot(page, "L11_open_on_map")
        check("Navigates to /explore", "/explore" in page.url, page.url)
        check("URL carries lat/lng/radius (cluster pre-opens)", "lat=" in page.url and "radius=" in page.url, page.url)

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 8. Delete list")
    page.goto(f"{BASE_UI}/lists", wait_until="networkidle", timeout=10000)
    time.sleep(0.5)
    # Expand first
    c2 = page.locator(".card").first
    if c2.count() > 0:
        c2.click()
        time.sleep(0.4)

    del_btn = page.locator("button[title='Delete list']").first
    check("Delete button present", del_btn.count() > 0)

    if del_btn.count() > 0:
        page.on("dialog", lambda d: d.accept())
        del_btn.click()
        time.sleep(1.5)
        shot(page, "L12_deleted")
        after_del = page.inner_text("body").lower()
        check("List gone after delete",
              "my koramangala picks" not in after_del and "koramangala thrift run" not in after_del,
              after_del[:150])
        check("Empty-state or no cards after delete",
              page.locator(".card").count() == 0 or "no lists" in after_del or "new list from explore" in after_del)

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 9. Explore sidebar shows list when one exists")
    stores_r = httpx.get(f"{BASE_API}/stores", params={"limit": 3}).json().get("stores", [])
    httpx.post(f"{BASE_API}/lists",
               json={"name": "Sidebar Test List", "store_ids": [s["id"] for s in stores_r]},
               headers=headers)

    page.goto(f"{BASE_UI}/explore", wait_until="networkidle", timeout=15000)
    time.sleep(2)
    shot(page, "L13_sidebar_with_list")

    sb2 = page.inner_text("body").lower()
    check("List appears in Explore sidebar 'Your lists'", "sidebar test list" in sb2, sb2[:200])

    sidebar_link = page.locator(".explore-aside a[href='/lists']").first
    check("Sidebar list item links to /lists", sidebar_link.count() > 0)

    # ═══════════════════════════════════════════════════════════════════════
    print("\n=== 10. Unauthenticated access gating")
    logout = page.locator("button:has-text('Log out'), button:has-text('LOG OUT')").first
    if logout.count() > 0:
        logout.click()
        time.sleep(0.8)

    page.goto(f"{BASE_UI}/lists", wait_until="networkidle", timeout=10000)
    shot(page, "L14_unauth")
    unauth = page.inner_text("body").lower()
    check("/lists gates unauthenticated users with login prompt", "log in" in unauth)
    check("No list content shown to logged-out user",
          "koramangala" not in unauth and page.locator(".card").count() == 0)

    browser.close()

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*55)
pc = sum(1 for s,_,_ in results if s == "PASS")
fc = sum(1 for s,_,_ in results if s == "FAIL")
print(f"RESULT: {pc}/{len(results)} passed, {fc} failed")
print(f"Screenshots: {SHOTS}")
if fc:
    print("\nFAILURES:")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"  X {label}: {detail.encode('ascii','replace').decode('ascii')[:120]}")

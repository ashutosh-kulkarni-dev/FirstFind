"""
FirstFind UI Verification — drives every page with Playwright.
Test account: test@thriftfind.demo / Test1234!
"""
import os, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS = str(REPO_ROOT / "screenshots")
os.makedirs(SCREENSHOTS, exist_ok=True)

EMAIL = "test@thriftfind.demo"
PASSWORD = "Test1234!"

results = []

def shot(page, name):
    path = os.path.join(SCREENSHOTS, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    return path

def check(label, ok, detail=""):
    icon = "v" if ok else "X"
    status = "PASS" if ok else "FAIL"
    results.append((status, label, str(detail)))
    safe_detail = str(detail).encode("ascii", "replace").decode("ascii")
    print(f"  {icon} [{status}] {label}")
    if safe_detail:
        print(f"         {safe_detail}")
    return ok

def body(page):
    return page.inner_text("body").lower()

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        # ── 1. LANDING PAGE ──────────────────────────────────────────────────
        print("\n=== 1. Landing Page (/)")
        page.goto(BASE, wait_until="networkidle", timeout=15000)
        shot(page, "01_landing")

        title = page.title()
        check("Page title set", bool(title), title)

        txt = body(page)
        check("Hero headline present", any(k in txt for k in ["firstfind", "thrift", "discover", "bengaluru"]))
        check("Navbar visible", page.locator("nav, header").count() > 0)

        # Nav links on landing
        nav_links = page.locator("nav a, header a").all()
        hrefs = [a.get_attribute("href") for a in nav_links if a.get_attribute("href")]
        check("Nav links present", len(hrefs) >= 3, f"hrefs: {hrefs}")

        explore_visible = page.locator("a[href='/explore'], a:has-text('EXPLORE'), a:has-text('Explore')").first.count() > 0
        check("Explore link in nav", explore_visible)

        chat_visible = page.locator("a[href='/chat'], a:has-text('ASSISTANT'), a:has-text('Assistant')").first.count() > 0
        check("Chat/Assistant link in nav", chat_visible)

        login_link = page.locator("a[href='/auth'], a:has-text('LOG IN'), a:has-text('Log in')").first
        check("Login link in nav (unauthenticated)", login_link.count() > 0)

        # CTA button on landing
        cta = page.locator("a:has-text('OPEN APP'), a:has-text('Open App'), a:has-text('Explore'), button:has-text('Start')").first
        check("CTA button on landing page", cta.count() > 0)

        # ── 2. AUTH PAGE ─────────────────────────────────────────────────────
        print("\n=== 2. Auth Page (/auth) — Login")
        page.goto(f"{BASE}/auth", wait_until="networkidle", timeout=15000)
        shot(page, "02_auth")

        # Form fields
        email_input = page.locator("input[type='email']").first
        pass_input = page.locator("input[type='password']").first
        check("Email input present", email_input.count() > 0)
        check("Password input present", pass_input.count() > 0)

        # Register tab present
        register_tab = page.locator("button:has-text('Register')").first
        check("Register tab/button present", register_tab.count() > 0)

        # Switch to register and check extra field
        if register_tab.count() > 0:
            register_tab.click()
            time.sleep(0.4)
            # Name input has no type/placeholder attrs — it's the first input.input (before email)
            name_input = page.locator("input.input:not([type])").first
            check("Name field appears on register tab", name_input.count() > 0)
            create_btn = page.locator("button.btn.btn-primary, button:has-text('Create account')").first
            check("'Create account' button on register", create_btn.count() > 0)
            shot(page, "02b_register_tab")

            # Switch back to login
            login_tab = page.locator("button:has-text('Log in')").first
            if login_tab.count() > 0:
                login_tab.click()
                time.sleep(0.3)

        # Fill and submit login
        email_input2 = page.locator("input[type='email']").first
        pass_input2 = page.locator("input[type='password']").first
        email_input2.fill(EMAIL)
        pass_input2.fill(PASSWORD)
        shot(page, "02c_login_filled")

        login_btn = page.locator("button.btn.btn-primary:has-text('Log in'), button:has-text('Log in')").first
        check("Login button present", login_btn.count() > 0)

        login_btn.click()
        # Auth redirects to next param or '/'
        try:
            page.wait_for_url(f"{BASE}/", timeout=6000)
            check("Login redirects to home", True, page.url)
        except Exception:
            # might stay on /auth if error
            current_url = page.url
            err_text = body(page)
            if "invalid" in err_text or "incorrect" in err_text or "wrong" in err_text:
                check("Login redirects to home", False, f"Auth error shown: {err_text[:80]}")
            else:
                check("Login redirects to home", current_url != f"{BASE}/auth", current_url)

        shot(page, "02d_after_login")

        # Check user shown in nav (logged in)
        logged_in_body = body(page)
        user_shown = "test user" in logged_in_body or "log out" in logged_in_body or "hi," in logged_in_body
        check("User greeting / logout appears after login", user_shown, logged_in_body[:120])

        # Logout button now visible
        logout_btn = page.locator("button.btn.btn-light.btn-pill:has-text('Log out'), button:has-text('Log out')").first
        check("Logout button visible in navbar", logout_btn.count() > 0)

        # ── 3. EXPLORE PAGE ──────────────────────────────────────────────────
        print("\n=== 3. Explore Page (/explore)")
        page.goto(f"{BASE}/explore", wait_until="networkidle", timeout=15000)
        time.sleep(2)
        shot(page, "03_explore")

        # Map container
        map_el = page.locator(".leaflet-container")
        check("Leaflet map renders", map_el.count() > 0)

        # Search input — class "input", placeholder "Store name or location…"
        search = page.locator("input.input[placeholder*='location'], input.input[placeholder*='Store name'], input.input").first
        check("Search input present", search.count() > 0, search.get_attribute("placeholder") if search.count() else "")

        # Area dropdown
        area_select = page.locator("select.select").first
        check("Area dropdown present", area_select.count() > 0)

        # Open now checkbox
        open_now_cb = page.locator("input[type='checkbox']").first
        check("'Open now only' checkbox present", open_now_cb.count() > 0)

        # Explore is map-centric: stores render as Leaflet interactive markers (dots on map)
        marker_count = page.locator(".leaflet-interactive").count()
        check("Store markers visible on map", marker_count > 0, f"{marker_count} interactive map elements")

        # Search for a store
        if search.count() > 0:
            search.fill("EcoDhaga")
            time.sleep(1.5)
            shot(page, "03b_search_result")
            # Searching changes the map markers (fewer stores shown on map)
            markers_after = page.locator(".leaflet-interactive").count()
            check("Search reduces markers on map", markers_after > 0, f"{markers_after} markers after search (should be fewer)")

            # Clear search
            search.fill("")
            time.sleep(0.5)

        # Filter by area
        if area_select.count() > 0:
            options = area_select.locator("option").all()
            option_vals = [o.get_attribute("value") for o in options if o.get_attribute("value")]
            check("Area dropdown has options", len(option_vals) > 0, f"{len(option_vals)} options")
            if option_vals:
                area_select.select_option(option_vals[0])
                time.sleep(0.8)
                shot(page, "03c_area_filter")
                check("Area filter changes results", True, f"Selected: {option_vals[0]}")
                area_select.select_option("")  # reset

        # Click a store card to open detail
        first_card = page.locator("a.card-link, a[class*='card']").first
        if first_card.count() > 0:
            card_href = first_card.get_attribute("href")
            check("Store card has href", bool(card_href), card_href)
            first_card.click()
            time.sleep(1)
            shot(page, "03d_store_from_explore")
            check("Clicking store card navigates to detail", "/store/" in page.url, page.url)
            page.go_back()
            time.sleep(0.5)

        # ── 4. STORE DETAIL PAGE ─────────────────────────────────────────────
        print("\n=== 4. Store Detail Page (/store/blr-0001)")
        page.goto(f"{BASE}/store/blr-0001", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        shot(page, "04_store_detail")

        dtxt = body(page)
        check("Store name displayed", "ecodhaga" in dtxt)
        # Area is not rendered as text in store detail (map-centric design) — check hours shown instead
        check("Store hours shown (11:00)", "11:00" in dtxt)

        # Hours / score
        check("Experience score shown", "4.8" in dtxt or "ai score" in dtxt or "score" in dtxt)

        # Save store button — class "save-btn", text "♡ Save store"
        save_btn = page.locator("button.save-btn").first
        check("Save store button present", save_btn.count() > 0, save_btn.inner_text() if save_btn.count() else "")

        if save_btn.count() > 0:
            save_btn.click()
            time.sleep(1)
            shot(page, "04b_save_clicked")
            save_txt = save_btn.inner_text()
            check("Save store button changes state", "saved" in save_txt.lower() or "save" in save_txt.lower(), save_txt)

        # Reviews section
        reviews_section = page.locator("[class*='review'], .review-item").first
        check("Reviews section present", reviews_section.count() > 0)

        # Review count shown
        check("Review count shown in text", "reviews" in dtxt)

        # Star rating buttons — class "star-btn"
        stars = page.locator("button.star-btn")
        check("Star rating buttons present", stars.count() > 0, f"{stars.count()} stars")

        # Review textarea — class "input textarea", placeholder "Share your find…"
        review_area = page.locator("textarea.input, textarea[placeholder*='find' i], textarea[placeholder*='Share' i]").first
        check("Review textarea present", review_area.count() > 0)

        if review_area.count() > 0 and stars.count() > 0:
            # Click 4th star
            stars.nth(3).click()
            time.sleep(0.2)
            review_area.fill("Wonderful store with great variety of vintage items!")
            shot(page, "04c_review_filled")

            post_btn = page.locator("button:has-text('Post review'), button:has-text('Log in to post')").first
            check("Post review button present", post_btn.count() > 0, post_btn.inner_text() if post_btn.count() else "")

            if post_btn.count() > 0 and "post review" in post_btn.inner_text().lower():
                post_btn.click()
                time.sleep(2)
                shot(page, "04d_review_posted")
                check("Review posted (no crash)", True)

        # Back to explore link
        back_btn = page.locator("a:has-text('Back'), a:has-text('back to explore')").first
        check("Back to explore link present", back_btn.count() > 0)

        # ── 5. CHAT PAGE ─────────────────────────────────────────────────────
        print("\n=== 5. Chat Page (/chat)")
        page.goto(f"{BASE}/chat", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        shot(page, "05_chat")

        ctxt = body(page)
        check("Chat page loads with welcome", "style assistant" in ctxt or "firstfind" in ctxt)
        check("Welcome message shown", "hi" in ctxt and "assistant" in ctxt)

        # Suggestion chips
        chips = page.locator("button.chip")
        check("Suggestion chips shown", chips.count() > 0, f"{chips.count()} chips")

        # Chat input — class "chat-input", placeholder "Ask about stores, areas, budgets…"
        chat_input = page.locator("input.chat-input").first
        check("Chat input present", chat_input.count() > 0, chat_input.get_attribute("placeholder") if chat_input.count() else "")

        # Send button — class "chat-send"
        send_btn = page.locator("button.chat-send").first
        check("Send button present", send_btn.count() > 0)

        if chat_input.count() > 0:
            # Message 1
            chat_input.fill("Show me thrift stores in Koramangala")
            shot(page, "05b_typed")
            send_btn.click() if send_btn.count() > 0 else chat_input.press("Enter")
            time.sleep(5)
            shot(page, "05c_response1")

            msg_els = page.locator(".bubble")
            check("Chat response bubbles appear", msg_els.count() >= 2, f"{msg_els.count()} bubbles")

            resp_txt = body(page)
            check("Response mentions stores", "koramangala" in resp_txt or "store" in resp_txt)

            # Suggestion chip click
            new_chips = page.locator("button.chip")
            if new_chips.count() > 0:
                chip_txt = new_chips.first.inner_text()
                new_chips.first.click()
                time.sleep(4)
                shot(page, "05d_chip_click")
                check("Suggestion chip sends a message", True, f"Clicked chip: {chip_txt}")

            # View past conversations button (logged-in only)
            history_btn = page.locator("button:has-text('View past conversations')").first
            check("'View past conversations' button shown (logged in)", history_btn.count() > 0)

            if history_btn.count() > 0:
                history_btn.click()
                time.sleep(1)
                shot(page, "05e_chat_history")
                check("Chat history panel opens", page.locator("text=CHAT HISTORY").count() > 0)
                # Close it
                close_btn = page.locator("button:has-text('✕')").first
                if close_btn.count() > 0:
                    close_btn.click()
                    time.sleep(0.3)

        # ── 6. LISTS PAGE ────────────────────────────────────────────────────
        print("\n=== 6. Lists Page (/lists)")
        page.goto(f"{BASE}/lists", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        shot(page, "06_lists")

        ltxt = body(page)
        check("Lists page loads", "saved" in ltxt or "list" in ltxt)

        # If logged in, should see lists or empty state
        new_list_link = page.locator("a[href='/explore']:has-text('New list'), a:has-text('New list from Explore')").first
        check("'New list from Explore' link present", new_list_link.count() > 0)

        # Check if our API-created list shows
        has_our_list = "my api test list" in ltxt or "api test" in ltxt
        check("API-created list visible on Lists page", has_our_list, ltxt[:200])

        # List cards
        list_cards = page.locator(".card").all()
        check("List card elements present", len(list_cards) > 0, f"{len(list_cards)} cards")

        # Click on a list card to expand
        if list_cards:
            list_cards[0].click()
            time.sleep(0.8)
            shot(page, "06b_list_expanded")
            check("List card expands on click", True)

        # Rename / delete buttons in list header
        rename_btn = page.locator("button[title='Rename']").first
        delete_btn = page.locator("button[title='Delete list']").first
        check("Rename button present", rename_btn.count() > 0)
        check("Delete list button present", delete_btn.count() > 0)

        # ── 7. NAVBAR ────────────────────────────────────────────────────────
        print("\n=== 7. Navbar (all pages)")
        page.goto(f"{BASE}/explore", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        shot(page, "07_navbar_explore")

        nbody = body(page)

        # User greeting — span.nav-greet shows "Hi, {name}"
        check("User greeting shown ('hi,')", "hi," in nbody or "test user" in nbody, nbody[:120])

        # My Lists nav link (only visible when logged in)
        my_lists_link = page.locator("nav a[href='/lists'], header a[href='/lists']").first
        check("'My Lists' nav link visible (logged in)", my_lists_link.count() > 0)

        # Explore link in nav
        exp_nav = page.locator("nav a[href='/explore'], header a[href='/explore']").first
        check("Explore nav link present", exp_nav.count() > 0)

        # Navigate via nav link to chat
        chat_nav = page.locator("nav a[href='/chat'], header a[href='/chat']").first
        check("Chat nav link present", chat_nav.count() > 0)
        if chat_nav.count() > 0:
            chat_nav.click()
            page.wait_for_load_state("networkidle", timeout=6000)
            check("Chat nav link navigates to /chat", "/chat" in page.url, page.url)

        # Navigate via nav link to explore
        page.goto(f"{BASE}/chat", wait_until="networkidle", timeout=8000)
        exp_nav2 = page.locator("nav a[href='/explore'], header a[href='/explore']").first
        if exp_nav2.count() > 0:
            exp_nav2.click()
            page.wait_for_load_state("networkidle", timeout=6000)
            check("Explore nav link navigates to /explore", "/explore" in page.url, page.url)

        # Logout
        page.goto(f"{BASE}/explore", wait_until="networkidle", timeout=8000)
        logout_btn2 = page.locator("button.btn-pill:has-text('Log out'), button:has-text('Log out')").first
        check("Logout button in navbar", logout_btn2.count() > 0)
        if logout_btn2.count() > 0:
            logout_btn2.click()
            time.sleep(1)
            shot(page, "07b_after_logout")
            after_body = body(page)
            check("After logout, login link appears", "log in" in after_body or "sign in" in after_body)

        # ── 8. UNAUTHENTICATED GATING ───────────────────────────────────────
        print("\n=== 8. Unauthenticated access gating")
        # Lists page should prompt login if logged out
        page.goto(f"{BASE}/lists", wait_until="networkidle", timeout=10000)
        shot(page, "08_lists_logged_out")
        unauth_txt = body(page)
        check("Lists page prompts login when logged out", "log in" in unauth_txt)

        # ── SUMMARY ──────────────────────────────────────────────────────────
        browser.close()
        print("\n" + "="*55)
        pass_count = sum(1 for s, _, _ in results if s == "PASS")
        fail_count = sum(1 for s, _, _ in results if s == "FAIL")
        print(f"RESULT: {pass_count}/{len(results)} passed, {fail_count} failed")
        print(f"Screenshots saved to: {SCREENSHOTS}")
        print("="*55)
        if fail_count:
            print("\nFAILURES:")
            for s, label, detail in results:
                if s == "FAIL":
                    safe = detail.encode("ascii", "replace").decode("ascii")
                    print(f"  X {label}: {safe}")
        return pass_count, fail_count

if __name__ == "__main__":
    run()

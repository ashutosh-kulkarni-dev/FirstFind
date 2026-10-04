from playwright.sync_api import sync_playwright
import time

BASE = "http://localhost:5173"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    # Test 1: Register name field
    page.goto(f"{BASE}/auth", wait_until="networkidle", timeout=15000)
    reg_btn = page.locator("button:has-text('Register')").first
    reg_btn.click()
    time.sleep(0.5)
    all_inputs = page.locator("input.input").all()
    print(f"Register form inputs (class=input): {len(all_inputs)}")
    for i, inp in enumerate(all_inputs):
        print(f"  [{i}] type={inp.get_attribute('type')} placeholder={inp.get_attribute('placeholder')}")

    # Test 2: Explore map markers
    page.goto(f"{BASE}/explore", wait_until="networkidle", timeout=15000)
    time.sleep(3)
    svg_paths = page.locator("svg path, svg circle").count()
    leaflet_interactive = page.locator(".leaflet-interactive").count()
    leaflet_marker = page.locator(".leaflet-marker-icon").count()
    print(f"Explore: svg elements={svg_paths}, leaflet-interactive={leaflet_interactive}, markers={leaflet_marker}")

    # Test 3: Store detail text
    page.goto(f"{BASE}/store/blr-0001", wait_until="networkidle", timeout=15000)
    time.sleep(1)
    txt = page.inner_text("body")
    safe = txt.encode("ascii", "replace").decode()
    print("Store detail body:\n" + safe[:400])

    browser.close()

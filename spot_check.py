from playwright.sync_api import sync_playwright
import time, os

SHOTS = r"c:\Users\Ashutosh Kulkarni\ThriftFind\screenshots\recs"
os.makedirs(SHOTS, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto("http://localhost:5173/store/blr-0001", wait_until="networkidle", timeout=15000)
    time.sleep(1)
    page.screenshot(path=os.path.join(SHOTS, "FINAL_shoppers_also_liked.png"), full_page=True)

    txt = page.inner_text("body").lower()
    match_count = page.locator("text=% match").count()
    print(f"'% match' elements on page: {match_count}")
    print(f"'shoppers' in page: {'shoppers' in txt}")
    print(f"'also liked' in page: {'also liked' in txt}")
    print("PASS" if match_count > 0 else "FAIL - match% still not showing")
    browser.close()

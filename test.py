from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=300
    )

    context = browser.new_context()
    page = context.new_page()

    page.goto("https://naver.com", timeout=60000)

    page.pause()
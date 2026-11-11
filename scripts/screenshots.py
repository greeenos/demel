"""Capture README screenshots from the in-browser demo (synthetic data only).

Usage: VITAL_TEST_URL=http://127.0.0.1:8208 .venv/bin/python scripts/screenshots.py
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

base = os.environ.get("VITAL_TEST_URL", "http://127.0.0.1:8208")
out = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
out.mkdir(parents=True, exist_ok=True)


def demo(page):
    page.goto(base)
    page.locator('[data-action=demo]').click()
    page.wait_for_timeout(2200)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)


def go(page, route, settle=2200):
    page.evaluate("r => { location.hash = r }", route)
    page.wait_for_timeout(settle)
    page.evaluate("window.scrollTo(0, 0)")


with sync_playwright() as p:
    browser = p.chromium.launch()
    phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, color_scheme="dark")
    page = phone.new_page()
    page.goto(base)
    page.wait_for_timeout(1200)
    page.screenshot(path=out / "mobile-login.png")
    demo(page)
    page.screenshot(path=out / "mobile-today.png")
    page.locator('.water-card').first.scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0, -150)")
    page.wait_for_timeout(500)
    page.screenshot(path=out / "mobile-hydration.png")
    go(page, '#health')
    page.screenshot(path=out / "mobile-health.png")
    page.locator('[data-action="tab:sleep"]').click()
    page.wait_for_timeout(2200)
    page.screenshot(path=out / "mobile-sleep.png")
    go(page, '#nutrition')
    page.screenshot(path=out / "mobile-nutrition.png")
    go(page, '#workouts')
    page.screenshot(path=out / "mobile-training.png")
    go(page, '#coach')
    page.screenshot(path=out / "mobile-coach.png")

    desk = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2, color_scheme="dark")
    page = desk.new_page()
    page.goto(base)
    page.wait_for_timeout(1200)
    page.screenshot(path=out / "desktop-login.png")
    demo(page)
    page.screenshot(path=out / "desktop-today.png")
    go(page, '#health')
    page.locator('[data-action="tab:trends"]').click()
    page.wait_for_timeout(2400)
    page.screenshot(path=out / "desktop-trends.png")
    go(page, '#coach')
    page.screenshot(path=out / "desktop-coach.png")
    browser.close()
print("saved to", out)

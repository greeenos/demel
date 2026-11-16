"""Full-screen sip reminder (the former Drinky) against the isolated local database only.

Needs the isolated backend: DATA_DIR=data-browser PORT=8208 APP_URL=http://127.0.0.1:8208
and VITAL_TEST_PASSWORD set to its password.
"""
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from backend import db  # noqa: E402

url = os.environ.get("VITAL_TEST_URL", "http://127.0.0.1:8208")
password = os.environ["VITAL_TEST_PASSWORD"]
db.DATA_DIR = root / "data-browser"
db.init()
db.put("hydration_settings", {"enabled": True, "sip_ml": 50, "start": 0, "end": 1440, "days": list(range(7))})
db.put("hydration_schedule", {})
shots = root / "review"
shots.mkdir(exist_ok=True)
errors = []


def water_today():
    day = date.today().isoformat()
    return sum(e["data"]["ml"] for e in db.entries(day, day) if e["kind"] == "water")


token = httpx.post(url + "/api/auth/device", json={"password": password}).json()["token"]
bearer = {"Authorization": "Bearer " + token}
before = water_today()

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("PW_CHROMIUM") or None)  # any Chromium if Playwright's is missing

    # 1. The phone app: a due sip covers the app; Done logs one sip and clears it.
    phone = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    phone.on("pageerror", lambda e: errors.append("phone: " + str(e)))
    phone.goto(url)
    phone.locator("[name=password]").fill(password)
    phone.locator("#login-form button").click()
    expect(phone.locator(".water-card")).to_be_visible()
    expect(phone.locator(".sip-overlay")).to_have_count(0)
    httpx.post(url + "/api/hydration/remind", headers=bearer)
    expect(phone.locator(".sip-overlay h1")).to_have_text("Time for a sip", timeout=8000)
    assert phone.evaluate("document.documentElement.scrollWidth<=innerWidth")
    phone.screenshot(path=str(shots / "sip-overlay-mobile.png"))
    phone.locator("[data-sip=drink]").click()
    expect(phone.locator(".sip-overlay")).to_have_count(0, timeout=8000)
    assert water_today() == before + 50, water_today()

    # 2. The desktop overlay window: #device=<token> logs in without a password and leaves the URL.
    desk = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    desk.on("pageerror", lambda e: errors.append("desktop: " + str(e)))
    desk.goto(f"{url}/?overlay=1&desktop=1#device={token}")
    expect(desk.locator(".sip-overlay.calm h1")).to_have_text("All caught up", timeout=8000)
    assert "device=" not in desk.url
    expect(desk.locator(".sip-overlay.calm a")).to_have_count(0)  # no "Open Demel" inside the desktop overlay

    # 3. "Remind everywhere now" from the phone shows up on the desktop over SSE; snooze there clears the phone.
    httpx.post(url + "/api/hydration/remind", headers=bearer)
    expect(desk.locator(".sip-overlay h1")).to_have_text("Time for a sip", timeout=8000)
    expect(desk.locator("[data-sip=fullscreen]")).to_have_count(0)  # the desktop window already covers the screen
    desk.screenshot(path=str(shots / "sip-overlay-desktop.png"))
    expect(phone.locator(".sip-overlay")).to_have_count(1, timeout=8000)
    desk.keyboard.press("Escape")  # Esc = in 5 min
    expect(desk.locator(".sip-overlay.calm")).to_have_count(1, timeout=8000)
    expect(phone.locator(".sip-overlay")).to_have_count(0, timeout=8000)

    # 4. A plain browser tab (not the desktop app) offers full screen; no session means a login hint.
    tab = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    tab.goto(f"{url}/?overlay=1")
    expect(tab.locator(".sip-overlay h1")).to_have_text("Log in first")

    browser.close()

assert not errors, errors
print({"status": "passed", "flows": ["phone overlay + done", "device token adopt", "remind everywhere over SSE", "esc snooze clears all", "login hint"]})

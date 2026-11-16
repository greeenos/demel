"""Desktop app + full-screen sip overlay (the former Drinky, merged into Demel)."""
import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from backend import db, hydration, notifications
from backend.models import Profile

PASSWORD = "test-password-12345"


def device(client):
    r = client.post("/api/auth/device", json={"password": PASSWORD})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_device_token_works_without_cookie_and_dies_with_password_change(client):
    assert client.post("/api/auth/device", json={"password": "wrong"}).status_code == 401
    auth = device(client)
    client.cookies.clear()
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers=auth).status_code == 200
    assert client.get("/api/auth/status", headers=auth).json() == {"authenticated": True}
    # A desktop window swaps #device=<token> for the normal httponly cookie.
    assert client.post("/api/auth/adopt").status_code == 401
    r = client.post("/api/auth/adopt", headers=auth)
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/state").status_code == 200
    # Changing the password logs out every other session, devices included.
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert client.post("/api/auth/password", json={"current": PASSWORD, "password": "another-password-123"}).status_code == 200
    assert client.get("/api/state", headers=auth).status_code == 401


def test_tray_actions_remind_drink_presence(logged):
    db.put("profile", Profile(water_goal=2000).model_dump(mode="json"))
    s = logged.post("/api/hydration/remind").json()
    assert s["due"] and s["goal"] == 2000  # "Remind everywhere now" ignores the reminder hours
    s = logged.post("/api/hydration/drink").json()  # no body: one sip of the configured size
    assert s["total"] == 50 and not s["due"]
    s = logged.post("/api/hydration/drink", json={"ml": 250}).json()
    assert s["total"] == 300
    assert logged.post("/api/hydration/drink", json={"ml": 0}).status_code == 422
    assert sorted(e["data"]["ml"] for e in db.entries() if e["kind"] == "water") == [50, 250]
    assert not hydration.at_computer()
    assert logged.post("/api/hydration/presence").json() == {"ok": True}
    assert hydration.at_computer()
    logged.post("/api/hydration/remind")
    assert logged.post("/api/hydration/skip").json()["due"] is False


def test_phone_push_waits_while_someone_is_at_the_computer(tmp_path, monkeypatch):
    # Not using the client fixture: it replaces notifications.tick with a stub.
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    db.init()
    db.put("profile", Profile(notify_enabled=True, water_reminders=True, morning_time="06:00", evening_time="23:00").model_dump(mode="json"))
    sent = []
    monkeypatch.setattr(notifications, "send", lambda title, body, tag, url: sent.append((tag, url)) or 1)
    hydration.remind(Profile())
    monkeypatch.setattr(hydration, "_presence", hydration.time.time())
    notifications.tick()
    assert sent == []  # the desktop overlay is enough
    monkeypatch.setattr(hydration, "_presence", 0.0)
    notifications.tick()
    assert len(sent) == 1 and sent[0][0].startswith("sip-") and sent[0][1] == "/?overlay=1"


def test_forced_reminder_survives_quiet_hours_until_answered(logged):
    p = Profile(water_goal=2000)
    night = datetime(2026, 11, 10, 23, 30, tzinfo=ZoneInfo("Europe/Prague"))
    assert not hydration.status(p, night)["due"]
    assert hydration.remind(p, night)["due"]
    assert not hydration.postpone(p, "snooze", night)["due"]  # outside the hours it does not come back


def test_events_stream_sends_live_state(logged):
    lines = []

    def read():
        with logged.stream("GET", "/api/hydration/events") as r:
            assert r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                if line.startswith("data: "):
                    lines.append(json.loads(line[6:]))
                    return

    t = threading.Thread(target=read, daemon=True)
    t.start()
    t.join(10)
    assert lines and set(lines[0]) == {"due", "next_at", "total", "goal", "remaining", "sip_ml", "enabled"}

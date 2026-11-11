import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import webpush, WebPushException
from py_vapid import Vapid

from . import db, hydration
from .models import Profile
from .scores import dashboard

log = logging.getLogger("vital")


def init_keys():
    if not db.secret("vapid_private"):
        key = ec.generate_private_key(ec.SECP256R1())
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        db.secret("vapid_private", private)
        db.put("vapid_public", base64.urlsafe_b64encode(public).rstrip(b"=").decode())


def valid_subscription(subscription):
    url = urlparse(subscription.get("endpoint", ""))
    host = url.hostname or ""
    allowed = host == "fcm.googleapis.com" or host.endswith(".push.apple.com") or host.endswith(".push.services.mozilla.com")
    keys = subscription.get("keys", {})
    if url.scheme != "https" or url.port not in (None, 443) or url.username or not allowed:
        raise ValueError("Invalid push server")
    for field, length in (("p256dh", 65), ("auth", 16)):
        value = keys.get(field, "")
        try:
            decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except Exception:
            raise ValueError("Invalid push keys")
        if len(decoded) != length:
            raise ValueError("Invalid push keys")


def contact():
    """VAPID `sub`: Apple rejects made-up mail domains; py_vapid rejects URLs with a port."""
    url = urlparse(os.environ.get("APP_URL", ""))
    return f"https://{url.hostname}" if url.scheme == "https" and url.hostname else "mailto:admin@localhost"


def send(title, body, tag="vital", url="/#today"):
    with db.db() as c:
        subscriptions = c.execute("SELECT subscription FROM push").fetchall()
    key = Vapid.from_pem(db.secret("vapid_private").encode()) if subscriptions else None
    count = 0
    for row in subscriptions:
        sub = json.loads(row[0])
        try:
            webpush(subscription_info=sub, data=json.dumps({"title": title, "body": body, "tag": tag, "url": url}),
                    vapid_private_key=key, vapid_claims={"sub": contact()}, timeout=15)
            count += 1
        except WebPushException as exc:
            response = exc.response
            if response is not None and response.status_code in (404, 410):
                with db.db() as c:
                    c.execute("DELETE FROM push WHERE endpoint=?", (sub["endpoint"],))
            # The push service explains rejections in the body, e.g. Apple's {"reason":"BadJwtToken"}.
            log.warning("Push failed (HTTP %s): %s", response.status_code if response is not None else "network",
                        (response.text[:200] if response is not None else str(exc)[:200]))
    return count


def tick():
    profile = Profile.model_validate(db.get("profile", {}))
    if not profile.notify_enabled:
        return
    local = datetime.now(ZoneInfo(profile.timezone))
    day = local.date().isoformat()
    minute = local.hour * 60 + local.minute

    def due(value):
        h, m = map(int, value.split(":"))
        return 0 <= minute - (h * 60 + m) < 5

    morning, workout = due(profile.morning_time), profile.workout_reminders and due("16:00")
    today, scores = {}, {}
    if morning or workout:
        # Only the last month matters for today's scores; loading all history every minute grows forever.
        state = dashboard(db.entries((local.date() - timedelta(days=31)).isoformat(), day), profile, day)
        today, scores = state["today"], state["scores"]
    notices = []
    if morning:
        recovery = scores.get("recovery")
        text = "Your morning summary is ready."
        if recovery is not None:
            text = f"Today's recovery: {recovery} %. " + ("Consider an easier day." if recovery < 40 else "Take a look at your sleep and plan for the day.")
        notices.append(("morning", "Good morning", text, "/#today"))
    if due(profile.evening_time):
        notices.append(("evening", "Time to wind down", "Log your day and get ready for sleep.", "/#health"))
    water = hydration.status(profile, local)
    if profile.water_reminders and water["due"]:
        notices.append(("sip-" + str(int(water["next_at"])), "Time for some water", f"Have {water['settings']['sip_ml']} ml, then confirm it in the app.", "/#nutrition"))
    if workout and not today.get("workout_minutes"):
        notices.append(("workout", "Room to move", "No activity logged yet today. A walk counts too.", "/#workouts"))
    for tag, title, body, url in notices:
        key = day + ":" + tag
        with db.db() as c:
            if c.execute("SELECT 1 FROM sent WHERE key=?", (key,)).fetchone():
                continue
        if send(title, body, tag, url):
            with db.db() as c:
                c.execute("INSERT OR IGNORE INTO sent VALUES(?,?)", (key, db.now()))


async def scheduler():
    from .google_health import sync
    counter = 0
    while True:
        try:
            day = datetime.now().date().isoformat()
            if db.get("backup_day") != day:
                await asyncio.to_thread(db.backup)
                db.put("backup_day", day)
            await asyncio.to_thread(tick)
            if counter % 60 == 0 and db.secret("google_tokens"):
                await sync()
        except Exception as exc:
            log.warning("Scheduled job failed: %s", type(exc).__name__)
        counter += 1
        await asyncio.sleep(60)

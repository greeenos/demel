import asyncio
import hashlib
import json
import secrets
import time
from datetime import date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from . import db, google_data
from .models import Entry, Profile

SCOPES = " ".join("https://www.googleapis.com/auth/googlehealth." + s + ".readonly" for s in
                  ("activity_and_fitness", "sleep", "health_metrics_and_measurements", "nutrition", "irn", "ecg", "profile", "settings"))
LOCK = asyncio.Lock()


def api_error(response, typ):
    try:
        error = response.json().get("error", {})
        details = error.get("details", []) if isinstance(error, dict) else []
        reasons = {d.get("reason") for d in details if isinstance(d, dict)}
    except (ValueError, AttributeError, TypeError):
        reasons = set()
    if "SERVICE_DISABLED" in reasons:
        message = "The Google Health API is not enabled in your Google Cloud project. Enable health.googleapis.com, wait a few minutes and sync again."
    elif "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in reasons:
        message = "Missing permissions. Reconnect your Google account and allow every requested data category."
    elif "ACCOUNT_NOT_LINKED" in reasons:
        message = "The Google account is not linked to Google Health. Sign in with the same account in the Google Health mobile app."
    else:
        message = f"Google HTTP {response.status_code}"
    return f"{typ}: {message}"


def authorize_url(base_url, session):
    client = db.secret("google_client_id")
    if not client or not db.secret("google_client_secret"):
        raise ValueError("First save the Google OAuth Client ID and Client secret in settings.")
    state = secrets.token_urlsafe(32)
    db.put("oauth_pending", {"state": state, "session": hashlib.sha256(session.encode()).hexdigest(), "expires": time.time() + 600})
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client, "redirect_uri": base_url + "/api/google/callback", "response_type": "code",
        "scope": SCOPES, "state": state, "access_type": "offline", "prompt": "consent"})


async def exchange(code, base_url):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={"client_id": db.secret("google_client_id"),
            "client_secret": db.secret("google_client_secret"), "code": code, "grant_type": "authorization_code",
            "redirect_uri": base_url + "/api/google/callback"})
        if r.status_code != 200:
            raise ValueError("Google sign-in failed. Check the OAuth project and redirect URI.")
        tokens = r.json()
        if not tokens.get("refresh_token"):
            raise ValueError("Google did not return a long-lived token. Try connecting the account again.")
        tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
        db.secret("google_tokens", json.dumps(tokens))


async def access_token(client):
    raw = db.secret("google_tokens")
    if not raw:
        raise ValueError("No Google account is connected yet.")
    tokens = json.loads(raw)
    if tokens.get("expires_at", 0) < time.time() + 90:
        r = await client.post("https://oauth2.googleapis.com/token", data={"client_id": db.secret("google_client_id"),
            "client_secret": db.secret("google_client_secret"), "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code != 200:
            raise ValueError("Google access expired or was revoked. Connect the account again.")
        tokens.update(r.json())
        tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
        db.secret("google_tokens", json.dumps(tokens))
    return tokens["access_token"]


def civil_day(value):
    if not value:
        raise ValueError("Google record has no date")
    d = value.get("date", value)
    return date(int(d["year"]), int(d["month"]), int(d["day"])).isoformat()


def session_day(interval, timezone, end=False):
    civil = interval.get("civilEndTime" if end else "civilStartTime")
    if civil:
        return civil_day(civil)
    timestamp = interval.get("endTime" if end else "startTime")
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(ZoneInfo(timezone)).date().isoformat()


def session_entry(point, key, timezone):
    value = point[key]
    interval = value["interval"]
    identifier = point.get("dataPointName") or point.get("name") or key + ":" + interval.get("startTime", json.dumps(interval, sort_keys=True))
    uid = "google-" + hashlib.sha256(identifier.encode()).hexdigest()[:32]
    if key == "sleep":
        summary = value.get("summary", {})
        if "minutesAsleep" not in summary:
            raise ValueError("Google sleep has no processed summary yet")
        data = {"minutes": float(summary["minutesAsleep"]),
                "in_bed_minutes": float(summary["minutesInSleepPeriod"]) if "minutesInSleepPeriod" in summary else None,
                "bedtime": interval.get("startTime", ""), "wake_time": interval.get("endTime", ""), "stages": []}
        for s in value.get("stages", []):
            if s.get("type") in ("AWAKE", "LIGHT", "DEEP", "REM", "ASLEEP", "RESTLESS"):
                a = datetime.fromisoformat(s["startTime"].replace("Z", "+00:00"))
                b = datetime.fromisoformat(s["endTime"].replace("Z", "+00:00"))
                data["stages"].append({"stage": s["type"], "minutes": (b - a).total_seconds() / 60})
        return Entry(id=uid, kind="sleep", day=session_day(interval, timezone, True), data=data, source="google")
    start = datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00"))
    metrics = value.get("metricsSummary", {})
    duration = float(value["activeDuration"].rstrip("s")) / 60 if value.get("activeDuration") else (end - start).total_seconds() / 60
    return Entry(id=uid, kind="workout", day=session_day(interval, timezone), source="google", data={
        "name": value.get("displayName") or value.get("exerciseType", "Aktivita"), "activity": value.get("exerciseType", "other").lower(),
        "minutes": duration, "calories": metrics.get("caloriesKcal"),
        "distance_km": metrics["distanceMillimeters"] / 1000000 if "distanceMillimeters" in metrics else None,
        "avg_hr": float(metrics["averageHeartRateBeatsPerMinute"]) if "averageHeartRateBeatsPerMinute" in metrics else None,
        "start": interval.get("startTime", ""), "end": interval.get("endTime", "")})


def merge_step_points(points):
    """{epoch_minute: steps}: each point spread evenly over its minutes, then the highest source per minute."""
    sources = {}
    for p in points:
        interval = p["steps"]["interval"]
        a = int(datetime.fromisoformat(interval["startTime"].replace("Z", "+00:00")).timestamp() // 60)
        b = max(a + 1, int(datetime.fromisoformat(interval["endTime"].replace("Z", "+00:00")).timestamp() // 60))
        per_source = sources.setdefault(json.dumps(p.get("dataSource", {}).get("platform")), {})
        for m in range(a, b):
            per_source[m] = per_source.get(m, 0) + int(p["steps"]["count"]) / (b - a)
    merged = {}
    for per_source in sources.values():
        for m, v in per_source.items():
            merged[m] = max(merged.get(m, 0), v)
    return merged


async def sync(days=30):
    async with LOCK:
        return await _sync(days)


async def _sync(days):
    profile = Profile.model_validate(db.get("profile", {}))
    today = datetime.now(ZoneInfo(profile.timezone)).date()
    last = db.get("google_last_sync")
    start = today - timedelta(days=days - 1)
    if last and days == 30 and db.get("google_archive_initialized"):
        # Re-read three days to pick up late sleep/activity edits and gaps after downtime.
        start = max(start, date.fromisoformat(last[:10]) - timedelta(days=2))
    end = today + timedelta(days=1)
    saved, errors = 0, []
    statuses = db.get("google_type_status", {})
    with db.db() as c:
        existing = c.execute("SELECT id,day,data FROM entries WHERE kind='vitals' AND source='google' AND day>=?", (start.isoformat(),)).fetchall()
    vitals = {r["day"]: json.loads(r["data"]) for r in existing}
    changed = set()
    mappings = [
        ("daily-resting-heart-rate", "dailyRestingHeartRate", "beatsPerMinute", "rhr"),
        ("daily-heart-rate-variability", "dailyHeartRateVariability", "averageHeartRateVariabilityMilliseconds", "hrv"),
        ("daily-oxygen-saturation", "dailyOxygenSaturation", "averagePercentage", "spo2"),
        ("daily-respiratory-rate", "dailyRespiratoryRate", "breathsPerMinute", "respiratory_rate"),
        ("daily-sleep-temperature-derivations", "dailySleepTemperatureDerivations", "nightlyTemperatureCelsius", "temperature"),
        ("daily-vo2-max", "dailyVo2Max", "vo2Max", "vo2max")]
    async with httpx.AsyncClient(timeout=45) as client:
        token = await access_token(client)
        headers = {"Authorization": "Bearer " + token}
        granted = set(json.loads(db.secret("google_tokens")).get("scope", "").split())

        def retain(typ, points):
            count = google_data.store(typ, points, start.isoformat(), end.isoformat(), profile.timezone)
            statuses[typ] = {"status": "available" if count else "no_data", "records": count, "at": db.now()}

        async def fetch_points(typ, filter_value):
            points, page_token = [], ""
            spec = google_data.SPEC[typ]
            for _ in range(200):
                params = {"pageSize": 25 if spec["record"] == "session" else 1000,
                          "dataSourceFamily": "users/me/dataSourceFamilies/google-wearables"}
                if filter_value:
                    params["filter"] = filter_value
                if typ not in ("sleep", "exercise") and spec["record"] != "daily":
                    params["dataSourceFamily"] = "users/me/dataSourceFamilies/all-sources"
                if page_token:
                    params["pageToken"] = page_token
                suffix = ":reconcile" if spec["method"] == "reconcile" else ""
                r = await client.get(f'https://health.googleapis.com/{spec["version"]}/users/me/dataTypes/{typ}/dataPoints{suffix}', params=params, headers=headers)
                if r.status_code != 200:
                    raise ValueError(api_error(r, typ))
                payload = r.json()
                points.extend(payload.get("dataPoints", []))
                next_token = payload.get("nextPageToken", "")
                if not next_token:
                    if spec["record"] != "food":
                        retain(typ, points)
                    return points
                if next_token == page_token:
                    raise ValueError(f"{typ}: repeated page token")
                page_token = next_token
            raise ValueError(f"{typ}: too many pages, shorten the period")

        for typ, key, field, dest in mappings:
            try:
                underscore = typ.replace("-", "_")
                points = await fetch_points(typ, f'{underscore}.date >= "{start}" AND {underscore}.date < "{end}"')
                for p in points:
                    v = p.get(key, {})
                    if field not in v:
                        continue
                    day = civil_day(v["date"])
                    vitals.setdefault(day, {})[dest] = float(v[field])
                    changed.add(day)
            except (ValueError, KeyError, httpx.HTTPError) as exc:
                errors.append(str(exc)[:400])

        for typ, key, field, dest in [("steps", "steps", "countSum", "steps"), ("active-energy-burned", "activeEnergyBurned", "kcalSum", "active_kcal")]:
            try:
                payload = {"range": {"start": {"date": {"year": start.year, "month": start.month, "day": start.day}},
                                     "end": {"date": {"year": end.year, "month": end.month, "day": end.day}}},
                           "windowSizeDays": 1, "pageSize": 90, "dataSourceFamily": "users/me/dataSourceFamilies/google-wearables"}
                r = await client.post(f"https://health.googleapis.com/v4/users/me/dataTypes/{typ}/dataPoints:dailyRollUp", json=payload, headers=headers)
                if r.status_code != 200:
                    raise ValueError(api_error(r, typ))
                points = r.json().get("rollupDataPoints", [])
                retain(typ, points)
                for p in points:
                    if field in p.get(key, {}):
                        day = civil_day(p["civilStartTime"])
                        value = float(p[key][field])
                        vitals.setdefault(day, {})[dest] = int(value) if dest == "steps" else value
                        changed.add(day)
            except (ValueError, KeyError, httpx.HTTPError) as exc:
                errors.append(str(exc)[:400])

        # Minute-level series power heart-rate zones, strain, stress and heart-rate recovery.
        # The API caps heart-rate roll-ups at 14 days per request, so the window is chunked.
        zone = ZoneInfo(profile.timezone)
        try:
            # Steps: the watch and the phone count the same walk, so the roll-ups keep only the watch.
            # Like the Google Health app, merge raw points from every source and keep the higher count per minute.
            points, page_token = [], ""
            for _ in range(200):
                params = {"pageSize": 1000, "dataSourceFamily": "users/me/dataSourceFamilies/all-sources",
                          "filter": f'steps.interval.civil_start_time >= "{start}" AND steps.interval.civil_start_time < "{end}"'}
                if page_token:
                    params["pageToken"] = page_token
                r = await client.get("https://health.googleapis.com/v4/users/me/dataTypes/steps/dataPoints", params=params, headers=headers)
                if r.status_code != 200:
                    raise ValueError(api_error(r, "steps (minutes)"))
                payload = r.json()
                points.extend(payload.get("dataPoints", []))
                page_token = payload.get("nextPageToken", "")
                if not page_token:
                    break
            merged = merge_step_points(points)
            google_data.store_minutes("steps-minutes", merged.items(), start.isoformat(), end.isoformat(), profile.timezone)
            totals = {}
            for m, v in merged.items():
                day = datetime.fromtimestamp(m * 60, zone).date().isoformat()
                totals[day] = totals.get(day, 0) + v
            for day, total in totals.items():
                if start.isoformat() <= day < end.isoformat() and total > vitals.get(day, {}).get("steps", 0):
                    vitals.setdefault(day, {})["steps"] = round(total)
                    changed.add(day)
        except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
            errors.append(str(exc)[:400])

        for typ, key, field in (("heart-rate", "heartRate", "beatsPerMinuteAvg"),):
            try:
                samples, cursor = [], datetime.combine(start, datetime.min.time(), zone)
                stop_at = datetime.combine(end, datetime.min.time(), zone)
                while cursor < stop_at:
                    chunk_end = min(stop_at, cursor + timedelta(days=14))
                    page_token = ""
                    for _ in range(40):
                        body = {"range": {"startTime": cursor.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z"),
                                          "endTime": chunk_end.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")},
                                "windowSize": "60s", "pageSize": 10000, "dataSourceFamily": "users/me/dataSourceFamilies/all-sources"}
                        if page_token:
                            body["pageToken"] = page_token
                        r = await client.post(f"https://health.googleapis.com/v4/users/me/dataTypes/{typ}/dataPoints:rollUp", json=body, headers=headers)
                        if r.status_code != 200:
                            raise ValueError(api_error(r, typ + " (minutes)"))
                        payload = r.json()
                        for p in payload.get("rollupDataPoints", []):
                            value = p.get(key, {}).get(field)
                            if value is not None and p.get("startTime"):
                                when = datetime.fromisoformat(p["startTime"].replace("Z", "+00:00"))
                                samples.append((int(when.timestamp() // 60), float(value)))
                        page_token = payload.get("nextPageToken", "")
                        if not page_token:
                            break
                    cursor = chunk_end
                google_data.store_minutes(typ + "-minutes", samples, start.isoformat(), end.isoformat(), profile.timezone)
            except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                errors.append(str(exc)[:400])

        for typ in ("sleep", "exercise"):
            try:
                # Google indexes sleep by wake time; exercise is indexed by start time.
                field = "civil_end_time" if typ == "sleep" else "civil_start_time"
                points = await fetch_points(typ, f'{typ}.interval.{field} >= "{start}" AND {typ}.interval.{field} < "{end}"')
                validated = []
                for p in points:
                    if typ in p:
                        entry = session_entry(p, typ, profile.timezone)
                        if start <= entry.day < end:
                            validated.append(entry)
                # Replace only after the entire type/window succeeds; removed upstream sessions disappear too.
                with db.db() as c:
                    kind = "workout" if typ == "exercise" else "sleep"
                    c.execute("DELETE FROM entries WHERE kind=? AND source='google' AND day>=? AND day<?", (kind, start.isoformat(), end.isoformat()))
                    for e in validated:
                        db.save(e, c)
                        saved += 1
            except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                errors.append(str(exc)[:400])
        core = {item[0] for item in mappings} | {"steps", "active-energy-burned", "sleep", "exercise"}
        for spec in google_data.CATALOG:
            typ = spec["type"]
            if typ in core:
                continue
            if f'https://www.googleapis.com/auth/googlehealth.{spec["scope"]}.readonly' not in granted:
                statuses[typ] = {"status": "needs_permission", "at": db.now()}
                continue
            if spec["version"] == "v4beta":
                statuses[typ] = {"status": "unsupported_device", "message": "This device does not provide this sensor type.", "at": db.now()}
                continue
            try:
                if spec["record"] == "account":
                    resource = "profile" if typ == "account-profile" else "settings"
                    r = await client.get(f"https://health.googleapis.com/v4/users/me/{resource}", headers=headers)
                    if r.status_code != 200:
                        raise ValueError(api_error(r, typ))
                    key = "accountProfile" if resource == "profile" else "accountSettings"
                    retain(typ, [{key: r.json(), "civilStartTime": {"date": {"year": today.year, "month": today.month, "day": today.day}}}])
                elif spec["rollup"]:
                    points = []
                    cursor = start
                    while cursor < end:
                        stop = min(end, cursor + timedelta(days=14))
                        r = await client.post(f"https://health.googleapis.com/v4/users/me/dataTypes/{typ}/dataPoints:dailyRollUp", headers=headers, json={
                            "range": {"start": {"date": {"year": cursor.year, "month": cursor.month, "day": cursor.day}},
                                      "end": {"date": {"year": stop.year, "month": stop.month, "day": stop.day}}},
                            "windowSizeDays": 1, "pageSize": 90, "dataSourceFamily": "users/me/dataSourceFamilies/all-sources"})
                        if r.status_code != 200:
                            raise ValueError(api_error(r, typ))
                        points.extend(r.json().get("rollupDataPoints", []))
                        cursor = stop
                    retain(typ, points)
                    if typ == "weight":
                        for point in points:
                            value = point.get("weight", {}).get("weightGramsAvg")
                            if value is not None:
                                day = civil_day(point["civilStartTime"])
                                vitals.setdefault(day, {})["weight"] = float(value) / 1000
                                changed.add(day)
                else:
                    prefix = typ.replace("-", "_")
                    field = {"daily": ".date", "sample": ".sample_time.civil_time", "interval": ".interval.civil_start_time", "session": ".interval.civil_start_time", "food": ""}[spec["record"]]
                    expression = f'{prefix}{field} >= "{start}" AND {prefix}{field} < "{end}"' if field else ""
                    points = await fetch_points(typ, expression)
                    if spec["record"] == "food":
                        annotated = [{**p, "civilStartTime": {"date": {"year": today.year, "month": today.month, "day": today.day}}} for p in points]
                        retain(typ, annotated)
            except (ValueError, KeyError, TypeError, httpx.HTTPError) as exc:
                statuses[typ] = {"status": "error", "message": str(exc)[:400], "at": db.now()}
    for day in changed:
        try:
            db.save(Entry(id="google-vitals-" + day, kind="vitals", day=day, source="google", data=vitals[day]))
            saved += 1
        except ValueError as exc:
            errors.append(f"{day}: {str(exc)[:120]}")
    stamp = db.now()
    if not errors:
        db.put("google_last_sync", stamp)
        db.put("google_archive_initialized", True)
    for error in errors:
        statuses[error.split(":", 1)[0]] = {"status": "error", "message": error, "at": stamp}
    db.put("google_type_status", statuses)
    result = {"saved": saved, "errors": errors, "at": stamp, "from": start.isoformat(), "to": today.isoformat()}
    db.put("google_sync_status", result)
    return result

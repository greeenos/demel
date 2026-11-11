"""Google measurements retained losslessly per day; numeric summaries power the UI."""
import json
import math
import re
import statistics
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import db

CATALOG = json.loads((Path(__file__).parent / "data/google-types.json").read_text())
FIELDS = json.loads((Path(__file__).parent / "data/google-fields.json").read_text())
SPEC = {s["type"]: s for s in CATALOG}
SKIP = {"date", "civilStartTime", "civilEndTime", "interval", "sampleTime", "createTime", "updateTime", "dataSource", "dataPointName", "name", "food"}


def payload(point, typ):
    key = re.sub(r"-([a-z0-9])", lambda m: m[1].upper(), typ)
    return point.get(key, {})


def point_day(point, typ, tz):
    if point.get("civilStartTime"):
        value = point["civilStartTime"]
    else:
        value = payload(point, typ)
        if value.get("date"):
            value = value["date"]
        elif value.get("interval"):
            interval = value["interval"]
            prefix = "End" if typ == "sleep" else "Start"
            value = interval.get("civil" + prefix + "Time") or interval.get(prefix.lower() + "Time")
        elif value.get("sampleTime"):
            value = value["sampleTime"].get("civilTime") or value["sampleTime"].get("physicalTime")
        else:
            raise ValueError(f"{typ}: Google record has no date")
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(tz))
        return parsed.astimezone(ZoneInfo(tz)).date().isoformat()
    d = value.get("date", value)
    return f'{int(d["year"]):04d}-{int(d["month"]):02d}-{int(d["day"]):02d}'


def numeric_fields(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            if key not in SKIP:
                yield from numeric_fields(child, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            tag = next((str(child[k]) for k in ("nutrient", "activityLevel", "heartRateZoneType", "type", "stage")
                        if isinstance(child, dict) and k in child), str(index))
            yield from numeric_fields(child, path + "." + tag)
    elif not isinstance(value, bool):
        try:
            if isinstance(value, str) and value.endswith("s"):
                number = float(value[:-1]) / 60
            else:
                number = float(value)
            if math.isfinite(number):
                yield path, number
        except (ValueError, TypeError):
            pass


def attributes(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            if key not in SKIP:
                yield from attributes(child, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for child in value:
            yield from attributes(child, path)
    elif isinstance(value, bool):
        yield path, "Ano" if value else "Ne"
    elif isinstance(value, str):
        try:
            float(value.rstrip("s"))
        except ValueError:
            yield path, value[:300]


def unit(field):
    lower = field.lower()
    if "vo2" in lower: return "ml/kg/min"
    if "millisecond" in lower: return "ms"
    if "beatsperminute" in lower: return "bpm"
    if "breathsperminute" in lower: return "/min"
    if "percentage" in lower: return "%"
    if "celsius" in lower: return "°C"
    if "kcal" in lower or "calories" in lower: return "kcal"
    if "millimeter" in lower: return "mm"
    if "grams" in lower: return "g"
    if "milliliter" in lower: return "ml"
    if "duration" in lower or "minute" in lower: return "min"
    return ""


def summarize(points, typ):
    values = defaultdict(list)
    for point in points:
        data = payload(point, typ) or point
        for key, number in numeric_fields(data):
            values[key].append(number)
        if typ in ("sedentary-period", "activity-level") and "interval" in data:
            interval = data["interval"]
            if interval.get("startTime") and interval.get("endTime"):
                a, b = (datetime.fromisoformat(interval[k].replace("Z", "+00:00")) for k in ("startTime", "endTime"))
                tag = data.get("activityLevel", "sedentary")
                values[tag + ".durationMinutes"].append((b-a).total_seconds()/60)
    return [{"field": key, "value": statistics.mean(numbers), "min": min(numbers), "max": max(numbers),
             "sum": sum(numbers), "count": len(numbers), "unit": unit(key), "description": FIELDS.get(key.split(".")[-1], "")}
            for key, numbers in sorted(values.items())]


def store(typ, points, start, end, tz):
    groups = defaultdict(list)
    for point in points:
        if not payload(point, typ):
            continue
        day = point_day(point, typ, tz)
        if start <= day < end:
            groups[day].append(point)
    with db.db() as c:
        c.execute("DELETE FROM google_days WHERE type=? AND day>=? AND day<?", (typ, start, end))
        for day, items in groups.items():
            c.execute("INSERT INTO google_days VALUES(?,?,?,?,?)", (typ, day, json.dumps(summarize(items, typ)),
                      zlib.compress(json.dumps(items, ensure_ascii=False).encode(), 6), db.now()))
    return sum(len(items) for items in groups.values())


MINUTE_TYPES = ("heart-rate-minutes", "steps-minutes")


def store_minutes(typ, samples, start, end, tz):
    """Keep one compact per-minute series per local day: [[epoch_minute, value], ...]."""
    groups = defaultdict(list)
    zone = ZoneInfo(tz)
    for minute, value in samples:
        day = datetime.fromtimestamp(minute * 60, zone).date().isoformat()
        if start <= day < end:
            groups[day].append([minute, round(value, 1)])
    with db.db() as c:
        c.execute("DELETE FROM google_days WHERE type=? AND day>=? AND day<?", (typ, start, end))
        for day, items in groups.items():
            items.sort()
            values = [v for _, v in items]
            summary = [{"field": "minutes", "value": len(items), "min": min(values), "max": max(values), "sum": sum(values),
                        "count": len(items), "unit": "min", "description": "Minutes with a value"}]
            c.execute("INSERT INTO google_days VALUES(?,?,?,?,?)", (typ, day, json.dumps(summary),
                      zlib.compress(json.dumps(items).encode(), 6), db.now()))
    return sum(len(v) for v in groups.values())


def minutes(typ, start, end):
    """Per-minute series between two local days (inclusive) as {epoch_minute: value}."""
    out = {}
    with db.db() as c:
        for r in c.execute("SELECT raw FROM google_days WHERE type=? AND day BETWEEN ? AND ?", (typ, start, end)):
            out.update({int(m): v for m, v in json.loads(zlib.decompress(r["raw"]))})
    return out


def summaries(start="1900-01-01", end="9999-12-31"):
    with db.db() as c:
        return [{"type": r["type"], "day": r["day"], "fields": json.loads(r["summary"]), "updated": r["updated"]}
                for r in c.execute("SELECT type,day,summary,updated FROM google_days WHERE day BETWEEN ? AND ? ORDER BY day", (start, end))]


def status(on):
    statuses = db.get("google_type_status", {})
    with db.db() as c:
        counts = {r["type"]: dict(r) for r in c.execute("SELECT type,count(*) AS days,max(day) AS last_day FROM google_days GROUP BY type")}
        selected = {r["type"]: json.loads(r["summary"]) for r in c.execute("SELECT type,summary FROM google_days WHERE day=?", (on,))}
    return [{**spec, **statuses.get(spec["type"], {"status": "not_synced"}),
             "days": counts.get(spec["type"], {}).get("days", 0), "last_day": counts.get(spec["type"], {}).get("last_day"),
             "fields": selected.get(spec["type"], [])} for spec in CATALOG]


def details(typ, day, offset=0):
    with db.db() as c:
        row = c.execute("SELECT * FROM google_days WHERE type=? AND day=?", (typ, day)).fetchone()
        history = [{"day": r["day"], "fields": json.loads(r["summary"])} for r in c.execute(
            "SELECT day,summary FROM google_days WHERE type=? AND day<=? ORDER BY day DESC LIMIT 90", (typ, day))]
    items = json.loads(zlib.decompress(row["raw"])) if row else []
    text = defaultdict(set)
    for item in items:
        for key, value in attributes(payload(item, typ)):
            if len(text[key]) < 25:
                text[key].add(value)
    return {"type": typ, "day": day, "fields": json.loads(row["summary"]) if row else [],
            "attributes": [{"field": key, "values": sorted(values)} for key,values in sorted(text.items())],
            "records": items[offset:offset+50], "count": len(items), "offset": offset, "history": list(reversed(history))}

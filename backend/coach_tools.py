"""Tools the AI coach may call to write into the health log.

Every call goes through the same pydantic validation as a manual entry. Daily
singletons (vitals, journal) are merged into the existing manual record of that
day instead of overwriting it. Writes are limited to the last 7 days.
"""
import json
from datetime import date, timedelta

from pydantic import ValidationError

from . import db, hydration
from .models import Entry

DAY = {"type": "string", "description": "Date YYYY-MM-DD. Omit for today."}

TOOLS = [
    {"type": "function", "function": {
        "name": "log_water", "description": "Log water (or an unsweetened drink) the user drank.",
        "parameters": {"type": "object", "properties": {"ml": {"type": "integer", "minimum": 1, "maximum": 3000}, "day": DAY}, "required": ["ml"]}}},
    {"type": "function", "function": {
        "name": "log_meal", "description": "Log food the user ate. Estimate nutrition for the WHOLE portion.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Meal name in the user's language"},
            "meal": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]},
            "grams": {"type": "number", "description": "Weight of the whole portion in grams"},
            "calories": {"type": "number"}, "protein": {"type": "number"}, "carbs": {"type": "number"},
            "fat": {"type": "number"}, "fiber": {"type": "number"},
            "notes": {"type": "string"}, "day": DAY},
            "required": ["name", "meal", "grams", "calories", "protein", "carbs", "fat"]}}},
    {"type": "function", "function": {
        "name": "log_workout", "description": "Log a completed workout or activity.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "activity": {"type": "string", "enum": ["strength", "running", "walking", "biking", "swimming", "yoga", "other"]},
            "minutes": {"type": "number"}, "rpe": {"type": "integer", "minimum": 1, "maximum": 10, "description": "Only if the user stated it"},
            "calories": {"type": "number"}, "distance_km": {"type": "number"}, "notes": {"type": "string"}, "day": DAY},
            "required": ["name", "activity", "minutes"]}}},
    {"type": "function", "function": {
        "name": "log_journal", "description": "Write or update the daily check-in (mood, energy, stress 1–5, caffeine, alcohol…).",
        "parameters": {"type": "object", "properties": {
            "mood": {"type": "integer", "minimum": 1, "maximum": 5}, "energy": {"type": "integer", "minimum": 1, "maximum": 5},
            "stress": {"type": "integer", "minimum": 1, "maximum": 5}, "caffeine": {"type": "integer", "description": "mg"},
            "meditation": {"type": "integer", "description": "minutes"}, "alcohol": {"type": "boolean"}, "illness": {"type": "boolean"},
            "notes": {"type": "string"}, "day": DAY}}}},
    {"type": "function", "function": {
        "name": "log_vitals", "description": "Log values the user measured by hand (weight, blood pressure, heart rate…). Only real measurements.",
        "parameters": {"type": "object", "properties": {
            "weight": {"type": "number", "description": "kg"}, "rhr": {"type": "number", "description": "resting heart rate, bpm"},
            "systolic": {"type": "integer"}, "diastolic": {"type": "integer"}, "spo2": {"type": "number"},
            "temperature": {"type": "number"}, "steps": {"type": "integer"}, "day": DAY}}}},
]

KINDS = {"log_water": "water", "log_meal": "meal", "log_workout": "workout", "log_journal": "journal", "log_vitals": "vitals"}


def _num(v, digits=1):
    return f"{v:.{digits}f}".rstrip("0").rstrip(".")


def label(kind, d):
    if kind == "water":
        return f"Water {d['ml']} ml"
    if kind == "meal":
        return f"{d['name']} · {_num(d['calories'], 0)} kcal"
    if kind == "workout":
        return f"{d['name']} · {_num(d['minutes'], 0)} min"
    if kind == "journal":
        return "Check-in"
    names = {"weight": ("Weight", "kg"), "rhr": ("Resting HR", "bpm"), "spo2": ("SpO₂", "%"), "temperature": ("Temperature", "°C"), "steps": ("Steps", "")}
    parts = [f"{names[k][0]} {_num(d[k])} {names[k][1]}".strip() for k in names if d.get(k) is not None]
    if d.get("systolic") and d.get("diastolic"):
        parts.append(f"BP {d['systolic']}/{d['diastolic']}")
    return ", ".join(parts) or "Measurement"


def run(call, today: date, profile):
    """Execute one tool call; returns a JSON-serialisable result for the model."""
    try:
        fn = call.get("function") or {}
        name = fn.get("name", "")
        args = json.loads(fn.get("arguments") or "{}")
        if name not in KINDS or not isinstance(args, dict):
            return {"ok": False, "error": "Unknown tool."}
        kind = KINDS[name]
        day = date.fromisoformat(args.pop("day")) if args.get("day") else today
        if day > today or day < today - timedelta(days=7):
            return {"ok": False, "error": "Only today and the last 7 days can be logged."}
        data = {k: v for k, v in args.items() if v is not None}
        if kind == "vitals" and not data:
            return {"ok": False, "error": "No measured value given."}
        entry_id = None
        if kind in ("vitals", "journal"):
            entry_id = f"manual-{kind}-{day.isoformat()}"
            with db.db() as c:
                row = c.execute("SELECT data FROM entries WHERE id=?", (entry_id,)).fetchone()
            if row:
                data = {**json.loads(row["data"]), **data}
        entry = Entry(kind=kind, day=day, data=data, id=entry_id)
        saved = db.save(entry)
        if kind == "water":
            hydration.postpone(profile, "skip")
        logged = {"kind": kind, "id": saved, "day": day.isoformat(), "label": label(kind, entry.data)}
        return {"ok": True, "saved": logged}
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)[:300]}

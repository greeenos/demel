"""Daily records merged per day, plus the dashboard summary built on backend.engine."""
import math
import statistics
from datetime import date, timedelta


def daily(entries):
    days = {}
    # Google first; a manual daily record explicitly overrides its non-null fields.
    for e in sorted(entries, key=lambda e: (e["source"] == "manual", e.get("updated", ""))):
        day = days.setdefault(e["day"], {"day": e["day"], "water": 0, "calories": 0, "protein": 0,
                                        "carbs": 0, "fat": 0, "fiber": 0, "workout_minutes": 0, "load": 0})
        d, kind = e["data"], e["kind"]
        if kind == "vitals":
            day.update({k: v for k, v in d.items() if v is not None})
        elif kind == "sleep":
            # Main sleep is selected by duration for Google; manual record takes precedence.
            if e["source"] == "manual" or "sleep" not in day or d["minutes"] > day["sleep"]["minutes"]:
                day["sleep"] = d
        elif kind == "meal":
            for key in ("calories", "protein", "carbs", "fat", "fiber"):
                day[key] += d.get(key, 0)
        elif kind == "water":
            day["water"] += d["ml"]
        elif kind == "workout":
            day["workout_minutes"] += d["minutes"]
            if d.get("rpe") is not None:
                day["load"] += d["minutes"] * d["rpe"]
        elif kind == "journal":
            day["journal"] = d
    return days


def clamp(v):
    return max(0, min(100, v))


def dashboard(entries, profile, on, hr=None, steps=None, measurements=None):
    """Rings for one day. Minute heart rate/steps are optional (tests and notifications may omit them)."""
    from .engine import compute
    days = daily(entries)
    current = days.get(on, {"day": on})
    rings = compute(days, entries, profile, on, hr, steps, measurements, detail=False)
    rec = rings["recovery"]
    result = {"sleep": rings["sleep"]["score"] if rings["sleep"] else None, "recovery": rec["score"],
              "strain": rings["strain"]["score"] if rings["strain"] else None, "baseline_days": rec["baseline_days"],
              "calibrating": rec["calibrating"], "target": rings["target"], "drivers": []}
    comp = rec.get("components") or {}
    if comp.get("hrv"):
        result["drivers"] = [{"name": "HRV", "value": comp["hrv"]["value"], "baseline": comp["hrv"]["baseline"]},
                             {"name": "Resting HR", "value": comp["rhr"]["value"], "baseline": comp["rhr"]["baseline"]}]
    history = []
    for i in range(89, -1, -1):
        key = (date.fromisoformat(on) - timedelta(days=i)).isoformat()
        if key in days:
            row = {k: v for k, v in days[key].items() if k not in ("sleep", "journal")}
            row["sleep_hours"] = round(days[key]["sleep"]["minutes"] / 60, 2) if days[key].get("sleep") else None
            history.append(row)
    correlations = []
    for tag, label in [("alcohol", "Alcohol"), ("illness", "Illness")]:
        groups = {True: [], False: []}
        for key, d in days.items():
            previous = (date.fromisoformat(key) - timedelta(days=1)).isoformat()
            journal = days.get(previous, {}).get("journal")
            if journal and d.get("sleep"):
                groups[journal.get(tag, False)].append(d["sleep"]["minutes"] / 60)
        if min(map(len, groups.values())) >= 3 and sum(map(len, groups.values())) >= 10:
            correlations.append({"label": label, "difference_hours": round(statistics.mean(groups[True]) - statistics.mean(groups[False]), 2),
                                 "with": len(groups[True]), "without": len(groups[False]), "note": "A pattern in your records, not proof of cause."})
    return {"today": current, "scores": result, "history": history, "correlations": correlations}

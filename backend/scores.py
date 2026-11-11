"""Transparent wellness heuristics; not Bevel algorithms or validated medical scores."""
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


def dashboard(entries, profile, on):
    days = daily(entries)
    current = days.get(on, {"day": on})
    before = [(date.fromisoformat(on) - timedelta(days=i)).isoformat() for i in range(1, 31)]
    baseline = [days[d] for d in before if d in days]
    sleep = current.get("sleep")
    sleep_score = round(clamp(100 * sleep["minutes"] / (profile.sleep_goal * 60))) if sleep else None
    result = {"sleep": sleep_score, "recovery": None, "strain": None, "baseline_days": 0, "drivers": []}
    paired = [d for d in baseline if d.get("hrv") is not None and d.get("rhr") is not None]
    result["baseline_days"] = len(paired)
    if len(paired) >= 14 and current.get("hrv") and current.get("rhr") and sleep_score is not None:
        log_hrvs = [math.log(d["hrv"]) for d in paired]
        hrs = [d["rhr"] for d in paired]
        hz = (math.log(current["hrv"]) - statistics.mean(log_hrvs)) / max(statistics.pstdev(log_hrvs), 0.10)
        rz = (current["rhr"] - statistics.mean(hrs)) / max(statistics.pstdev(hrs), 2)
        recovery = 50 + 15 * hz - 12 * rz + 0.25 * (sleep_score - 80)
        result["recovery"] = round(clamp(recovery))
        result["drivers"] = [{"name": "HRV", "value": current["hrv"], "baseline": round(math.exp(statistics.mean(log_hrvs)), 1)},
                             {"name": "Resting HR", "value": current["rhr"], "baseline": round(statistics.mean(hrs), 1)}]
    # session-RPE load is used only when the user supplied effort; missing RPE is not fabricated.
    if current.get("load", 0) > 0:
        result["strain"] = round(min(100, 100 * (1 - math.exp(-current["load"] / 400))))
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

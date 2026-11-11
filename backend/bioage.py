"""Biological age from wearable, lifestyle and blood biomarkers.

Structure follows Bevel's published description: five categories (Sleep, Activity, Fitness,
Lifestyle, Blood), four-week averages, weekly update on Monday, comparison with age/sex
benchmarks, published hazard ratios, an overlap correction and per-factor confidence.

Conversion of a hazard ratio into years uses the Gompertz law of mortality: adult all-cause
mortality rises by about 8.5 % per year of age (doubling time ≈ 8 years), so a relative risk HR
is equivalent to ln(HR)/0.085 years of ageing ("effective age", Spiegelhalter 2016).
"""
import math
import statistics
from datetime import date, timedelta

from .age import chronological_age, phenoage
from .analytics import FRIEND_MEDIANS

GOMPERTZ = 0.085          # ln-mortality increase per year of age
MUTUAL_ADJUSTMENT = 0.5   # single-exposure HRs are halved to approximate mutual adjustment of correlated habits
FACTOR_CAP = 4.0          # years, per factor
FULL_DAYS = 20            # Bevel: "at least 20 days of data in the past month" = full confidence

REFS = {
    "gompertz": ["Spiegelhalter 2016 – Effective age (BMJ)", "https://doi.org/10.1136/bmj.i5395"],
    "mrdt": ["Finch, Pike & Witten 1990 – Mortality-rate doubling time", "https://doi.org/10.1126/science.2382131"],
    "sleep": ["Wang et al. 2021 – Sleep duration and mortality (dose–response)", "https://pubmed.ncbi.nlm.nih.gov/33530979/"],
    "sleep_ref": ["Cappuccio et al. 2010 – Sleep duration meta-analysis", "https://doi.org/10.1093/sleep/33.5.585"],
    "sri": ["Windred et al. 2024 – Sleep regularity vs duration and mortality", "https://pubmed.ncbi.nlm.nih.gov/37995126/"],
    "sri_method": ["Phillips et al. 2017 – Sleep Regularity Index", "https://doi.org/10.1038/s41598-017-03171-4"],
    "steps": ["Saint-Maurice et al. 2020 – Steps, intensity and mortality", "https://jamanetwork.com/journals/jama/fullarticle/2763292"],
    "steps_plateau": ["Paluch et al. 2022 – Steps meta-analysis (Lancet Public Health)", "https://doi.org/10.1016/S2468-2667(21)00302-9"],
    "mvpa": ["Arem et al. 2015 – Leisure-time activity dose and mortality", "https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2212267"],
    "vigorous": ["Stamatakis et al. 2022 – Vigorous intermittent lifestyle activity (Nat Med)", "https://doi.org/10.1038/s41591-022-02100-x"],
    "strength": ["Momma et al. 2022 – Muscle-strengthening dose–response (BJSM)", "https://doi.org/10.1136/bjsports-2021-105061"],
    "strength2": ["Saeidifard et al. 2019 – Resistance training and mortality", "https://doi.org/10.1177/2047487319850718"],
    "vo2": ["Kodama et al. 2009 – Fitness and mortality (per MET)", "https://doi.org/10.1001/jama.2009.681"],
    "vo2_ref": ["Kaminsky et al. 2022 – FRIEND reference VO₂ max", "https://doi.org/10.1016/j.mayocp.2021.08.020"],
    "vo2_elite": ["Mandsager et al. 2018 – Fitness and long-term mortality", "https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2707428"],
    "rhr": ["Zhang et al. 2016 – Resting heart rate and mortality (per 10 bpm)", "https://pubmed.ncbi.nlm.nih.gov/26542543/"],
    "rhr_ref": ["Quer et al. 2020 – Wearable resting heart rate in 92,457 adults", "https://doi.org/10.1371/journal.pone.0227709"],
    "lbm": ["Li et al. 2021 – Lean body mass and mortality", "https://hub.hku.hk/bitstream/10722/304950/1/content.pdf"],
    "alcohol": ["Zhao et al. 2023 – Alcohol intake and mortality (JAMA Netw Open)", "https://doi.org/10.1001/jamanetworkopen.2023.6185"],
    "smoking": ["Jha et al. 2013 – 21st-century hazards of smoking and benefits of cessation", "https://doi.org/10.1056/NEJMsa1211128"],
    "fiber": ["Reynolds et al. 2019 – Carbohydrate quality and human health (Lancet)", "https://doi.org/10.1016/S0140-6736(18)31809-9"],
    "phenoage": ["Levine et al. 2018 – Phenotypic age (PhenoAge)", "https://pubmed.ncbi.nlm.nih.gov/29676998/"],
}


def hr_curve(anchors, x):
    """Log-linear interpolation of a hazard ratio between published anchor points; flat outside."""
    if x <= anchors[0][0]:
        return anchors[0][1]
    for (x0, h0), (x1, h1) in zip(anchors, anchors[1:]):
        if x <= x1:
            t = (x - x0) / (x1 - x0)
            return math.exp(math.log(h0) + t * (math.log(h1) - math.log(h0)))
    return anchors[-1][1]


def to_years(hr, ref_hr, adjust=True):
    years = math.log(hr / ref_hr) / GOMPERTZ * (MUTUAL_ADJUSTMENT if adjust else 1)
    return max(-FACTOR_CAP, min(FACTOR_CAP, years))


SLEEP_HOURS = [(5, 1.29), (6, 1.13), (7, 1.0), (8.5, 1.0), (10, 1.36)]
SRI = [(41, 1.53), (60, 1.0), (75, 0.90)]
# Paluch et al. 2022 pooled quartile medians (steps/day) and hazard ratios vs the lowest quartile.
STEPS = [(3553, 1.0), (5801, 0.60), (7842, 0.55), (10901, 0.47)]
MVPA = [(0, 1.0), (75, 0.80), (150, 0.69), (300, 0.63), (450, 0.61)]
VIGOROUS = [(0, 1.0), (10, 0.85), (30, 0.70), (60, 0.62)]
STRENGTH = [(0, 1.0), (10, 0.95), (30, 0.85), (60, 0.83), (140, 0.90), (200, 1.0)]


def friend_median(age, sex):
    medians = FRIEND_MEDIANS.get(sex)
    if not medians:
        return None
    pos = (age - 25) / 10
    if pos <= 0:
        return medians[0]
    if pos >= len(medians) - 1:
        return medians[-1]
    i = int(pos)
    return medians[i] + (medians[i + 1] - medians[i]) * (pos - i)


def factor(key, label, category, value, unit, years, days, refs, note, target=None):
    confidence = min(1.0, days / FULL_DAYS) if years is not None else 0.0
    return {"key": key, "label": label, "category": category, "value": value, "unit": unit,
            "years": round(years, 2) if years is not None else None, "weighted": round(years * confidence, 2) if years is not None else None,
            "days": days, "confidence": round(confidence, 2), "refs": [REFS[r] for r in refs], "note": note, "target": target}


def sleep_regularity(engine, days):
    agree = total = 0
    for d in days:
        nxt = engine.shift(d, 1)
        if not engine.sleep(d) or not engine.sleep(nxt):
            continue
        a, b = engine.asleep(d), engine.asleep(nxt)
        start = engine.midnight(d) - 720
        for t in range(start, start + 1440):
            agree += (t in a) == ((t + 1440) in b)
            total += 1
    return (round(200 * agree / total - 100, 1), total // 1440) if total else (None, 0)


def snapshot(engine, entries, profile, as_of):
    """Biological age as of a Monday, from the 28 days before it."""
    window = [engine.shift(as_of, -i) for i in range(28, 0, -1)]
    age = chronological_age(str(profile.birthdate) if profile.birthdate else None, as_of)
    if age is None or profile.sex not in ("male", "female"):
        return {"available": False, "reason": "Add your date of birth and sex in settings."}
    if age < 18:
        return {"available": False, "reason": "Biological age is available from 18 years."}
    sex, factors = profile.sex, []

    # Sleep ---------------------------------------------------------------------------
    nights = [engine.sleep(d)["minutes"] / 60 for d in window if engine.sleep(d)]
    if nights:
        h = statistics.mean(nights)
        factors.append(factor("sleep_time", "Time Asleep", "sleep", round(h, 2), "h", to_years(hr_curve(SLEEP_HOURS, h), 1.06), len(nights),
                              ["sleep", "sleep_ref"], "7–8.5 h is the lowest-risk plateau. The reference (HR 1.06) is the population-average excess risk with about a third of adults sleeping under 7 h.", "7–8.5 h"))
    else:
        factors.append(factor("sleep_time", "Time Asleep", "sleep", None, "h", None, 0, ["sleep"], "No sleep records in the last 4 weeks."))
    sri, pairs = sleep_regularity(engine, window)
    factors.append(factor("sleep_consistency", "Sleep Consistency", "sleep", sri, "SRI", to_years(hr_curve(SRI, sri), hr_curve(SRI, 70)) if sri is not None else None, pairs,
                          ["sri", "sri_method"], "Sleep Regularity Index: the chance of being in the same state (asleep/awake) 24 h apart. Above 70 subtracts years.", "> 70"))

    # Activity --------------------------------------------------------------------------
    step_days = [engine.days[d]["steps"] for d in window if engine.days.get(d, {}).get("steps") is not None]
    step_ref = 8000 if age < 60 else 6000
    if step_days:
        s = statistics.mean(step_days)
        factors.append(factor("steps", "Daily Steps (4-week average)", "activity", round(s), "steps/day", to_years(hr_curve(STEPS, s), hr_curve(STEPS, step_ref)), len(step_days),
                              ["steps_plateau", "steps"], f"Average of {len(step_days)} Fitbit days from {window[0]} to {window[-1]}, not today's count. Pooled cohort quartiles (Paluch 2022): benefits level off around {step_ref:,}+ steps a day at your age.", f"{step_ref:,}+"))
    else:
        factors.append(factor("steps", "Daily Steps", "activity", None, "steps", None, 0, ["steps"], "No step data."))
    hr_days = [d for d in window if engine.has_hr(d)]
    if hr_days:
        z23 = sum(engine.day_zones(d)[2] + engine.day_zones(d)[3] for d in hr_days) / len(hr_days) * 7
        z45 = sum(engine.day_zones(d)[4] + engine.day_zones(d)[5] for d in hr_days) / len(hr_days) * 7
        factors.append(factor("zone23", "Zones 2–3", "activity", round(z23), "min/week", to_years(hr_curve(MVPA, z23), hr_curve(MVPA, 150)), len(hr_days),
                              ["mvpa"], "Moderate intensity (60–79 % HRmax). 150+ minutes a week subtracts years.", "150+ min/wk"))
        factors.append(factor("zone45", "Zones 4–5", "activity", round(z45), "min/week", to_years(hr_curve(VIGOROUS, z45), hr_curve(VIGOROUS, 10)), len(hr_days),
                              ["vigorous"], "Vigorous intensity (≥80 % HRmax). Even 10+ minutes a week subtracts years.", "10+ min/wk"))
    else:
        for key, label in (("zone23", "Zones 2–3"), ("zone45", "Zones 4–5")):
            factors.append(factor(key, label, "activity", None, "min/week", None, 0, ["mvpa"], "Needs all-day heart rate."))
    strength = sum(w["minutes"] for d in window for w in engine.logged(d) if engine.is_strength(w.get("activity")))
    tracked = len(hr_days) or len(step_days)
    per_week = strength / 4
    factors.append(factor("strength", "Strength Training", "activity", round(per_week), "min/week",
                          to_years(hr_curve(STRENGTH, per_week), hr_curve(STRENGTH, 10)) if tracked else None, tracked,
                          ["strength", "strength2"], "Logged strength sessions. 10+ minutes a week subtracts years; the benefit peaks around 30–60 min.", "10+ min/wk"))

    # Fitness ---------------------------------------------------------------------------
    vo2 = [engine.days[d]["vo2max"] for d in window if engine.days.get(d, {}).get("vo2max")]
    if vo2:
        v, ref = statistics.median(vo2), friend_median(age, sex)
        years = max(-FACTOR_CAP, min(FACTOR_CAP, (v - ref) / 3.5 * math.log(0.87) / GOMPERTZ * MUTUAL_ADJUSTMENT))
        factors.append(factor("vo2max", "VO₂ Max", "fitness", round(v, 1), "ml/kg/min", years, max(len(vo2) * 4, FULL_DAYS if len(vo2) >= 3 else len(vo2) * 4),
                              ["vo2", "vo2_ref", "vo2_elite"], f"Compared with the FRIEND median for your age and sex ({ref:.1f}). Each 3.5 ml/kg/min (1 MET) ≈ 13 % lower mortality.", f"> {ref:.0f}"))
    else:
        factors.append(factor("vo2max", "VO₂ Max", "fitness", None, "ml/kg/min", None, 0, ["vo2"], "No device VO₂ max. The heart-rate estimate on the Fitness tab is not used here."))
    rhr = [engine.days[d]["rhr"] for d in window if engine.days.get(d, {}).get("rhr")]
    if rhr:
        r, ref = statistics.mean(rhr), (64 if sex == "male" else 67)
        years = max(-FACTOR_CAP, min(FACTOR_CAP, (r - ref) / 10 * math.log(1.09) / GOMPERTZ * MUTUAL_ADJUSTMENT * 2))
        factors.append(factor("rhr", "Resting Heart Rate", "fitness", round(r, 1), "bpm", years, len(rhr), ["rhr", "rhr_ref"],
                              f"Device resting heart rate vs the wearable average for your sex ({ref} bpm). Every 10 bpm ≈ 9 % higher mortality; not halved because heart rate is not a habit that overlaps the others.", f"< {ref}"))
    else:
        factors.append(factor("rhr", "Resting Heart Rate", "fitness", None, "bpm", None, 0, ["rhr"], "No resting heart rate."))
    lbm = lean_mass(engine, window, profile)
    factors.append(lbm)

    # Lifestyle -------------------------------------------------------------------------
    factors.append(nutrition(entries, window))
    factors.append(alcohol(entries, window, sex))
    factors.append(smoking(profile, as_of))

    # Blood -----------------------------------------------------------------------------
    factors.append(blood(entries, profile, as_of))

    categories = {}
    for cat, label, icon in (("sleep", "Sleep", "moon"), ("activity", "Activity", "workout"), ("fitness", "Fitness", "heart"),
                             ("lifestyle", "Lifestyle", "body"), ("blood", "Blood", "flask")):
        items = [f for f in factors if f["category"] == cat]
        usable = [f for f in items if f["weighted"] is not None]
        years = round(sum(f["weighted"] for f in usable), 1) if usable else None
        weight = 4 if cat == "blood" else 1
        categories[cat] = {"key": cat, "label": label, "icon": icon, "years": years, "factors": items,
                           "coverage": round(sum(f["confidence"] for f in items) / len(items), 2), "weight": weight * len(items)}
    total_weight = sum(4 if f["category"] == "blood" else 1 for f in factors)
    confidence = round(100 * sum(f["confidence"] * (4 if f["category"] == "blood" else 1) for f in factors) / total_weight)
    physio_days = max(len(nights), len(step_days), len(hr_days))
    delta = sum(c["years"] for c in categories.values() if c["years"] is not None)
    return {"available": physio_days >= 10, "calibrating": physio_days < FULL_DAYS, "reason": None if physio_days >= 10 else "Building your baseline: about 10–20 days of wearable data are needed.",
            "as_of": as_of, "window": [window[0], window[-1]], "chronological": round(age, 1), "biological": round(age + delta, 1),
            "difference": round(delta, 1), "confidence": confidence, "categories": categories, "data_days": physio_days}


def lean_mass(engine, window, profile):
    fat = [f for f in engine.measurements if f["type"] == "body-fat" and window[0] <= f["day"] <= window[-1]]
    weights = [engine.days[d]["weight"] for d in window if engine.days.get(d, {}).get("weight")]
    height = profile.height_cm
    if not fat or not weights or not height:
        return factor("lean_mass", "Lean Body Mass", "fitness", None, "kg", None, 0, ["lbm"], "Needs body-fat percentage, weight and height.")
    pct = statistics.mean(next((x["value"] for x in f["fields"] if x["field"] == "bodyFatPercentageAvg"), None) or 0 for f in fat)
    lbm = statistics.mean(weights) * (1 - pct / 100)
    index = lbm / (height / 100) ** 2
    anchors = [(16, 1.44), (18.5, 1.0), (21, 0.86)] if profile.sex == "male" else [(13, 1.44), (15, 1.0), (17, 0.86)]
    return factor("lean_mass", "Lean Body Mass", "fitness", round(lbm, 1), "kg", to_years(hr_curve(anchors, index), 1.0), FULL_DAYS if len(fat) >= 2 else 10,
                  ["lbm"], f"Lean mass index {index:.1f} kg/m² compared with a typical adult of your sex.")


def nutrition(entries, window):
    complete = {e["day"] for e in entries if e["kind"] == "nutrition_day" and e["data"].get("complete") and window[0] <= e["day"] <= window[-1]}
    fiber = {}
    for e in entries:
        if e["kind"] == "meal" and e["day"] in complete:
            fiber[e["day"]] = fiber.get(e["day"], 0) + e["data"].get("fiber", 0)
    if len(fiber) < 5:
        return factor("nutrition", "Nutrition (fiber)", "lifestyle", None, "g/day", None, len(fiber), ["fiber"],
                      "Log every meal and mark at least 5 days complete. Fiber is used as the evidence-based nutrition marker.")
    g = statistics.mean(fiber.values())
    years = to_years(math.exp((g - 20) / 8 * math.log(0.93)), 1.0)
    return factor("nutrition", "Nutrition (fiber)", "lifestyle", round(g, 1), "g/day", years, len(fiber) * 3, ["fiber"],
                  "Each 8 g/day of dietary fiber ≈ 7 % lower mortality; reference 20 g/day (typical intake).", "25–30 g")


def alcohol(entries, window, sex):
    days = {}
    for e in entries:
        if e["kind"] == "journal" and window[0] <= e["day"] <= window[-1]:
            d = e["data"]
            if d.get("alcohol_drinks") is not None:
                days[e["day"]] = d["alcohol_drinks"]
            elif d.get("alcohol") is False:
                days[e["day"]] = 0
    limit = 4 if sex == "male" else 2
    if len(days) < 7:
        return factor("alcohol", "Alcohol", "lifestyle", None, "drinks/week", None, len(days), ["alcohol"],
                      f"Log drinks in the journal on at least 7 days. Up to {limit} a week adds nothing.", f"≤ {limit}/wk")
    per_week = sum(days.values()) / len(days) * 7
    anchors = [(limit, 1.0), (31.5, 1.15), (45.5, 1.34)] if sex == "male" else [(limit, 1.0), (17.5, 1.24), (31.5, 1.35)]
    years = to_years(hr_curve(anchors, per_week), 1.0)
    return factor("alcohol", "Alcohol", "lifestyle", round(per_week, 1), "drinks/week", years, min(FULL_DAYS, len(days) * 1.5), ["alcohol"],
                  f"A drink = 10 g of alcohol. Up to {limit} a week adds nothing; risk rises above about 25 g a day.", f"≤ {limit}/wk")


def smoking(profile, as_of):
    status = getattr(profile, "smoking", "unknown")
    if status == "unknown":
        return factor("smoking", "Smoking", "lifestyle", None, "", None, 0, ["smoking"], "Answer the smoking question in settings.")
    if status == "never":
        return factor("smoking", "Smoking", "lifestyle", "Never", "", 0.0, FULL_DAYS, ["smoking"], "Never smoked: no years added.")
    per_day = profile.cigarettes_per_day or 10
    excess = 2.0 * min(1.5, per_day / 20)
    label = f"{per_day}/day"
    if status == "former":
        quit_years = max(0, int(as_of[:4]) - (profile.quit_year or int(as_of[:4])))
        excess *= math.exp(-quit_years / 5)
        label = f"Quit {quit_years} y ago"
    years = min(10.0, math.log(1 + excess) / GOMPERTZ)
    return factor("smoking", "Smoking", "lifestyle", label, "", years, FULL_DAYS, ["smoking"],
                  "Current smoking roughly triples mortality; quitting before 40 removes about 90 % of the excess, fading over the years.")


def blood(entries, profile, as_of):
    labs = sorted((e for e in entries if e["kind"] == "lab" and e["day"] <= as_of), key=lambda e: e["day"])
    if not labs:
        return factor("phenoage", "Blood (PhenoAge)", "blood", None, "years", None, 0, ["phenoage"], "Add a blood test with all 9 PhenoAge markers.")
    lab = labs[-1]
    age = chronological_age(str(profile.birthdate) if profile.birthdate else None, lab["day"])
    if age is None or age < 20:
        return factor("phenoage", "Blood (PhenoAge)", "blood", None, "years", None, 0, ["phenoage"], "PhenoAge is defined from age 20.")
    result = phenoage(lab["data"], age)
    months = (date.fromisoformat(as_of) - date.fromisoformat(lab["day"])).days / 30.4
    fresh = 1.0 if months < 3 else 0.75 if months < 6 else 0.5 if months < 12 else 0.0
    out = factor("phenoage", "Blood (PhenoAge)", "blood", result["age"], "years", result["difference"] * 0.5, FULL_DAYS * fresh, ["phenoage"],
                 f"Blood test from {lab['day']}: PhenoAge {result['age']:.1f} vs {age:.1f}. Half the difference counts because blood and wearable markers overlap; older tests count less (≥12 months: not used).")
    return out


def biological_age(engine, entries, profile, on):
    today = date.fromisoformat(on)
    monday = today - timedelta(days=today.weekday())
    current = snapshot(engine, entries, profile, monday.isoformat())
    previous = snapshot(engine, entries, profile, (monday - timedelta(days=7)).isoformat())
    history = []
    for weeks in range(7, -1, -1):
        d = (monday - timedelta(days=7 * weeks)).isoformat()
        s = current if weeks == 0 else previous if weeks == 1 else snapshot(engine, entries, profile, d)
        if s.get("available"):
            history.append({"day": d, "biological": s["biological"], "chronological": s["chronological"]})
    if current.get("available") and previous.get("available"):
        current["change"] = round(current["biological"] - previous["biological"], 1)
    current["next_update_days"] = (monday + timedelta(days=7) - today).days
    current["history"] = history
    current["method"] = {"gompertz": GOMPERTZ, "mutual_adjustment": MUTUAL_ADJUSTMENT, "cap": FACTOR_CAP, "refs": [REFS["gompertz"], REFS["mrdt"]]}
    return current

"""Daily physiology engine: heart-rate zones, Strain, Recovery, Sleep, Stress, Energy, HRR and training load.

The structure mirrors what Bevel publishes about its scores (inputs, bands, zone definition);
Bevel does not publish formulas, so every formula below is built from the cited research and
any app-specific calibration constant is labelled as such in METHODS.
"""
import math
import statistics
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .age import chronological_age

# Calibration: 100·(1−e^(−TRIMP/210)) maps a 10 h day with 80 min of hard football (Edwards TRIMP ≈ 600) to ~94 %.
STRAIN_K = 210.0
ZONE_EDGES = (.5, .6, .7, .8, .9)  # % of HRmax, Bevel default (Restorative, Z1–Z5)

METHODS = {
    "zones": {"title": "Heart-rate zones", "text": "Minute heart rate as % of HRmax: Restorative <50 %, Z1 50–59, Z2 60–69, Z3 70–79, Z4 80–89, Z5 ≥90 %. HRmax = 220 − age (Fox 1971; Bevel's default) or your highest observed minute if higher.",
              "refs": [["Fox, Naughton & Haskell 1971", "https://pubmed.ncbi.nlm.nih.gov/4929133/"], ["Tanaka, Monahan & Seals 2001 (HRmax review)", "https://doi.org/10.1016/S0735-1097(00)01054-8"]]},
    "strain": {"title": "Strain", "text": "Edwards TRIMP over every waking minute (minutes × zone number, 1–5), then a diminishing-return curve 100·(1 − e^(−TRIMP/210)). Passive strain comes from all-day heart rate, active strain from workouts. The constant 210 is this app's calibration, not a published value.",
               "refs": [["Edwards 1993 – Summated heart-rate zones (TRIMP)", "https://www.worldcat.org/title/27921669"], ["Foster et al. 2001 – Monitoring exercise training", "https://pubmed.ncbi.nlm.nih.gov/11708692/"]]},
    "target": {"title": "Target strain", "text": "Built from your 14-day average daily load (TRIMP) and today's Recovery: lower = chronic × (0.2 + 0.4·R), upper = chronic × (0.9 + 0.6·R), R = recovery/100. Grounded in the acute:chronic workload sweet spot (0.8–1.3) and HRV-guided training, where hard sessions are placed on well-recovered days.",
               "refs": [["Gabbett 2016 – Training–injury prevention paradox", "https://doi.org/10.1136/bjsports-2015-095788"], ["Kiviniemi et al. 2007 – HRV-guided training", "https://doi.org/10.1007/s00421-007-0552-2"], ["Vesterinen et al. 2016 – Individual HRV-guided training", "https://doi.org/10.1249/MSS.0000000000000910"]]},
    "recovery": {"title": "Recovery", "text": "Morning readiness from last night's HRV (ln RMSSD) and sleeping heart rate compared with your previous 30 days (z-scores), plus the Sleep score; elevated breathing rate, a rise in skin temperature or low SpO₂ subtract. Composite c = 0.5·z(lnHRV) − 0.25·z(sleep HR) + 0.25·(Sleep−75)/15 − penalties; Recovery = 100·Φ(0.25 + 1.1·c). Needs 7 baseline nights (calibrating until 14).",
                 "refs": [["Plews et al. 2013 – Training adaptation and HRV (ln rMSSD)", "https://doi.org/10.1007/s40279-013-0071-8"], ["Buchheit 2014 – Monitoring training status with HR measures", "https://doi.org/10.3389/fphys.2014.00073"], ["Mishra et al. 2020 – Pre-symptomatic detection with wearables", "https://doi.org/10.1038/s41551-020-00640-6"], ["Miller et al. 2020 – Respiratory rate rises before illness", "https://doi.org/10.1371/journal.pone.0243693"], ["Smarr et al. 2020 – Wearable temperature and fever onset", "https://doi.org/10.1038/s41598-020-78355-6"]]},
    "sleep": {"title": "Sleep score", "text": "Time asleep vs tonight's need 35 %, deep sleep vs age/sex target 15 %, REM vs 20 % 10 %, efficiency (≥85 % full marks) 15 %, continuity (wake after sleep onset ≤20 min full, ≥51 min zero) 10 %, heart-rate dip vs the previous day (≥10 % full) 15 %. Missing parts are re-weighted. Bands: <70 poor, 70–85 normal, >85 excellent. Sleep need = goal + ¼ of the last 7 nights' debt (max 90 min).",
              "refs": [["Ohayon et al. 2017 – NSF sleep quality recommendations", "https://doi.org/10.1016/j.sleh.2016.11.006"], ["Ohayon et al. 2004 – Sleep architecture across the lifespan", "https://doi.org/10.1093/sleep/27.7.1255"], ["Hirshkowitz et al. 2015 – NSF sleep duration", "https://doi.org/10.1016/j.sleh.2014.12.010"], ["Kitamura et al. 2016 – Recovery from sleep debt", "https://doi.org/10.1038/srep35812"], ["Ben-Dov et al. 2007 – Blunted heart-rate dip and mortality", "https://doi.org/10.1001/archinte.167.19.2116"]]},
    "stress": {"title": "Stress", "text": "Physical stress 1–100 from waking heart rate above your sleeping baseline, relative to your heart-rate reserve: 100·(HR − sleep HR)/(0.5·(HRmax − sleep HR)), smoothed over 5 minutes. Exercise (detected or logged sessions) is reported as active stress and kept out of the daily average and lowest value. Bands: <30 low, 30–60 medium, >60 high.",
               "refs": [["Myrtek 2004 – Additional (non-metabolic) heart rate in daily life", "https://doi.org/10.1027/0269-8803.18.2.102"], ["Verkuil et al. 2016 – Non-metabolic HRV reduction as a stress marker", "https://doi.org/10.1007/s12160-016-9787-2"], ["Thayer et al. 2012 – HRV meta-analysis and stress", "https://doi.org/10.1016/j.neubiorev.2011.11.009"]]},
    "energy": {"title": "Energy", "text": "An app model, not a validated measure: you wake with 0.55·Recovery + 0.45·Sleep, every waking minute drains 0.06 % plus 0.14 %·(stress/100)², and draining slows as the tank empties.",
               "refs": []},
    "hrr": {"title": "Heart-rate recovery", "text": "Drop in heart rate 2 minutes after a workout that ended in zone 4+. ≤22 bpm at 2 minutes is associated with higher mortality.",
            "refs": [["Cole et al. 1999 – HRR and mortality", "https://doi.org/10.1056/NEJM199910283411804"], ["Shetler et al. 2001 – 2-minute HRR", "https://doi.org/10.1016/S0735-1097(01)01519-4"]]},
    "load": {"title": "Training load", "text": "Workout TRIMP per day; acute load = 7-day exponentially weighted average, chronic = 42-day. Optimal acute load = 0.8–1.3 × chronic. Calibrating until 10 training days in 6 weeks. Muscular load uses strength sessions (heart-rate TRIMP or session-RPE × minutes ÷ 2).",
             "refs": [["Banister et al. 1975 – Fitness–fatigue model", "https://www.worldcat.org/title/2442556"], ["Hulin et al. 2016 – Acute:chronic workload ratio", "https://doi.org/10.1136/bjsports-2015-094817"], ["Gabbett 2016", "https://doi.org/10.1136/bjsports-2015-095788"]]},
    "kcal": {"title": "Workout energy", "text": "Energy from heart rate, weight, age and sex (Keytel equation) when the device did not provide it.",
             "refs": [["Keytel et al. 2005", "https://doi.org/10.1080/02640410470001730089"]]},
    "vo2": {"title": "VO₂ max estimate", "text": "When no device VO₂ max exists: 15.3 × HRmax / resting HR. A rough estimate (± ~10 %); not used for biological age.",
            "refs": [["Uth et al. 2004", "https://doi.org/10.1007/s00421-003-0988-y"]]},
}


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def epoch_minute(text):
    if not text:
        return None
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() // 60)
    except ValueError:
        return None


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


class Engine:
    """Computes per-day physiology from daily records and minute heart rate / steps."""

    def __init__(self, days, entries, profile, on, hr=None, steps=None, measurements=None):
        self.days, self.entries, self.p, self.on = days, entries, profile, on
        self.tz = ZoneInfo(profile.timezone)
        self.hr, self.steps = hr or {}, steps or {}
        self.measurements = measurements or []
        self.age = chronological_age(str(profile.birthdate) if profile.birthdate else None, on)
        observed = max(self.hr.values()) if self.hr else 0
        predicted = 220 - self.age if self.age else 190
        self.hrmax = round(max(predicted, observed), 1)
        self.weight = next((self.days[d]["weight"] for d in sorted(self.days, reverse=True) if self.days[d].get("weight")), None)
        self._cache = {}

    # --- time helpers ---------------------------------------------------------
    def midnight(self, day):
        return int(datetime.combine(date.fromisoformat(day), datetime.min.time(), self.tz).timestamp() // 60)

    def shift(self, day, n):
        return (date.fromisoformat(day) + timedelta(days=n)).isoformat()

    def clock(self, minute):
        return datetime.fromtimestamp(minute * 60, self.tz).strftime("%H:%M")

    def memo(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def zone(self, bpm):
        pct = bpm / self.hrmax
        return sum(pct >= edge for edge in ZONE_EDGES)

    # --- sleep windows ---------------------------------------------------------
    def sleep(self, day):
        return self.days.get(day, {}).get("sleep")

    def sleep_window(self, day):
        s = self.sleep(day)
        if not s:
            return None
        a, b = epoch_minute(s.get("bedtime")), epoch_minute(s.get("wake_time"))
        return (a, b) if a is not None and b is not None and b > a else None

    def asleep(self, day):
        """Asleep minutes reconstructed from the ordered stage list (falls back to the whole window)."""
        def build():
            window, s = self.sleep_window(day), self.sleep(day)
            if not window:
                return set()
            out, cursor = set(), window[0]
            if s.get("stages"):
                for st in s["stages"]:
                    n = int(round(st["minutes"]))
                    if st["stage"] != "AWAKE":
                        out.update(range(cursor, cursor + n))
                    cursor += n
                return {m for m in out if m < window[1]}
            return set(range(*window))
        return self.memo(("asleep", day), build)

    def awake_minutes(self, day):
        def build():
            start, end = self.midnight(day), self.midnight(self.shift(day, 1))
            blocked = set()
            for d in (day, self.shift(day, 1)):
                w = self.sleep_window(d)
                if w:
                    blocked.update(range(*w))
            return [m for m in range(start, end) if m not in blocked]
        return self.memo(("awake", day), build)

    # --- heart-rate derived -----------------------------------------------------
    def zone_minutes(self, minutes):
        counts = [0] * 6
        for m in minutes:
            if m in self.hr:
                counts[self.zone(self.hr[m])] += 1
        return counts

    @staticmethod
    def trimp(counts):
        return sum(i * n for i, n in enumerate(counts))

    def day_zones(self, day):
        return self.memo(("zones", day), lambda: self.zone_minutes(self.awake_minutes(day)))

    def has_hr(self, day):
        return sum(self.day_zones(day)) >= 240

    def strain(self, day):
        def build():
            if self.has_hr(day):
                load = self.trimp(self.day_zones(day))
            else:
                # Without minute heart rate fall back to session-RPE (Foster 2001) on Edwards' scale.
                load = sum(w["minutes"] * w["rpe"] / 2 for w in self.logged(day) if w.get("rpe"))
                if not load:
                    return None
            return {"score": round(100 * (1 - math.exp(-load / STRAIN_K))), "trimp": round(load), "hr": self.has_hr(day)}
        return self.memo(("strain", day), build)

    def sleeping_hr(self, day):
        def build():
            values = [self.hr[m] for m in self.asleep(day) if m in self.hr]
            return round(statistics.mean(values), 1) if len(values) >= 60 else None
        return self.memo(("shr", day), build)

    def waking_hr(self, day):
        def build():
            values = [self.hr[m] for m in self.awake_minutes(day) if m in self.hr]
            return round(statistics.mean(values), 1) if len(values) >= 120 else None
        return self.memo(("whr", day), build)

    def rhr(self, day):
        """Resting HR as the mean sleeping heart rate (what Bevel reports), else the device value."""
        return self.sleeping_hr(day) or self.days.get(day, {}).get("rhr")

    def value(self, key, day):
        if key == "rhr":
            return self.rhr(day)
        if key == "sleep_minutes":
            s = self.sleep(day)
            return s["minutes"] if s else None
        return self.days.get(day, {}).get(key)

    def baseline(self, key, day, n=30, fn=None):
        out = []
        for i in range(1, n + 1):
            d = self.shift(day, -i)
            v = fn(d) if fn else self.value(key, d)
            if v is not None:
                out.append(v)
        return out

    # --- sleep score -----------------------------------------------------------
    def deep_target(self):
        female = self.p.sex == "female"
        hi, lo = (0.14, 0.10) if female else (0.13, 0.09)
        if self.age is None:
            return 0.125
        return hi - (hi - lo) * clamp((self.age - 30) / 40)

    def sleep_need(self, day):
        goal = self.p.sleep_goal * 60
        debt = 0.0
        for i in range(1, 8):
            s = self.sleep(self.shift(day, -i))
            if s:
                debt += goal - s["minutes"]
        repay = min(90.0, max(0.0, debt) / 4)
        return {"minutes": round(goal + repay), "goal": round(goal), "debt": round(max(0.0, debt)), "repay": round(repay)}

    def sleep_bank(self, day):
        goal = self.p.sleep_goal * 60
        nights = [self.sleep(self.shift(day, -i)) for i in range(0, 7)]
        nights = [n for n in nights if n]
        return round(sum(n["minutes"] - goal for n in nights)) if nights else None

    def sleep_score(self, day):
        def build():
            s = self.sleep(day)
            if not s:
                return None
            need = self.sleep_need(day)
            parts = {}
            parts["duration"] = (0.35, clamp((s["minutes"] / need["minutes"] - 0.5) / 0.45))
            stages = s.get("stages") or []
            totals = {}
            for st in stages:
                totals[st["stage"]] = totals.get(st["stage"], 0) + st["minutes"]
            if s.get("in_bed_minutes"):
                eff = s["minutes"] / s["in_bed_minutes"]
                parts["efficiency"] = (0.15, clamp((eff - 0.65) / 0.20))
            if stages:
                inner = stages[:]
                while inner and inner[0]["stage"] == "AWAKE":
                    inner.pop(0)
                while inner and inner[-1]["stage"] == "AWAKE":
                    inner.pop()
                waso = sum(st["minutes"] for st in inner if st["stage"] == "AWAKE")
                parts["continuity"] = (0.10, clamp((51 - waso) / 31))
                if totals.get("DEEP") is not None or totals.get("REM") is not None:
                    parts["deep"] = (0.15, clamp(totals.get("DEEP", 0) / s["minutes"] / self.deep_target()))
                    parts["rem"] = (0.10, clamp(totals.get("REM", 0) / s["minutes"] / 0.20))
            sleep_hr, day_hr = self.sleeping_hr(day), self.waking_hr(self.shift(day, -1))
            dip = None
            if sleep_hr and day_hr:
                dip = 1 - sleep_hr / day_hr
                parts["hr_dip"] = (0.15, clamp(dip / 0.10))
            weight = sum(w for w, _ in parts.values())
            score = round(100 * sum(w * v for w, v in parts.values()) / weight)
            asleep = s["minutes"]
            return {"score": score, "band": "Excellent" if score > 85 else "Normal" if score >= 70 else "Poor",
                    "parts": {k: round(100 * v) for k, (_, v) in parts.items()}, "need": need, "bank": self.sleep_bank(day),
                    "asleep": asleep, "in_bed": s.get("in_bed_minutes"), "efficiency": round(100 * asleep / s["in_bed_minutes"]) if s.get("in_bed_minutes") else None,
                    "deep_pct": round(100 * totals.get("DEEP", 0) / asleep, 1) if stages else None,
                    "rem_pct": round(100 * totals.get("REM", 0) / asleep, 1) if stages else None,
                    "deep_target": round(100 * self.deep_target(), 1), "hr_dip": round(100 * dip, 1) if dip is not None else None,
                    "bedtime": s.get("bedtime"), "wake_time": s.get("wake_time")}
        return self.memo(("sleep", day), build)

    # --- recovery --------------------------------------------------------------
    @staticmethod
    def z(value, history, min_sd):
        if value is None or len(history) < 3:
            return None
        sd = max(statistics.pstdev(history), min_sd)
        return max(-3.0, min(3.0, (value - statistics.mean(history)) / sd))

    def recovery(self, day):
        def build():
            hrv, rhr = self.value("hrv", day), self.rhr(day)
            pairs = [d for d in (self.shift(day, -i) for i in range(1, 31)) if self.value("hrv", d) and self.rhr(d)]
            result = {"score": None, "baseline_days": len(pairs), "calibrating": len(pairs) < 14, "components": {}}
            sleep = self.sleep_score(day)
            if len(pairs) < 7 or not hrv or not rhr or sleep is None:
                return result
            z_hrv = self.z(math.log(hrv), [math.log(self.value("hrv", d)) for d in pairs], 0.10)
            z_rhr = self.z(rhr, [self.rhr(d) for d in pairs], 2.0)
            sleep_c = clamp((sleep["score"] - 75) / 15, -3, 3)
            c = 0.5 * z_hrv - 0.25 * z_rhr + 0.25 * sleep_c
            penalties = {}
            rr = self.value("respiratory_rate", day)
            z_rr = self.z(rr, self.baseline("respiratory_rate", day), 0.5)
            if z_rr is not None and z_rr > 1.5:
                penalties["respiratory_rate"] = round(0.3 * (z_rr - 1.5), 2)
            temp = self.value("temperature", day)
            temps = self.baseline("temperature", day)
            if temp is not None and len(temps) >= 5 and temp - statistics.mean(temps) > 0.5:
                penalties["temperature"] = round(0.6 * (temp - statistics.mean(temps) - 0.5) + 0.2, 2)
            spo2 = self.value("spo2", day)
            if spo2 is not None and spo2 < 94:
                penalties["spo2"] = round(0.15 * (94 - spo2), 2)
            c -= sum(penalties.values())
            score = round(clamp(100 * phi(0.25 + 1.1 * c), 1, 100))
            result.update({"score": score, "band": "High" if score >= 67 else "Medium" if score >= 34 else "Low",
                           "components": {"hrv": {"value": hrv, "baseline": round(math.exp(statistics.mean(math.log(self.value('hrv', d)) for d in pairs)), 1), "z": round(z_hrv, 2)},
                                          "rhr": {"value": rhr, "baseline": round(statistics.mean(self.rhr(d) for d in pairs), 1), "z": round(z_rhr, 2)},
                                          "sleep": {"value": sleep["score"]}, "penalties": penalties}})
            return result
        return self.memo(("recovery", day), build)

    # --- target strain -----------------------------------------------------------
    def target_strain(self, day):
        loads = [s["trimp"] for s in (self.strain(self.shift(day, -i)) for i in range(1, 15)) if s]
        rec = self.recovery(day)["score"]
        if len(loads) < 5 or rec is None:
            return None
        chronic, r = statistics.mean(loads), rec / 100
        to_pct = lambda t: round(100 * (1 - math.exp(-t / STRAIN_K)))
        return {"low": to_pct(chronic * (0.2 + 0.4 * r)), "high": to_pct(chronic * (0.9 + 0.6 * r)), "chronic_trimp": round(chronic)}

    # --- stress & energy ---------------------------------------------------------
    def rest_hr(self, day):
        values = [self.sleeping_hr(self.shift(day, -i)) for i in range(0, 14)]
        values = [v for v in values if v]
        return statistics.median(values) if values else self.days.get(day, {}).get("rhr")

    def stress(self, day):
        def build():
            rest = self.rest_hr(day)
            minutes = [m for m in self.awake_minutes(day) if m in self.hr]
            if not rest or len(minutes) < 60:
                return None
            span = 0.5 * (self.hrmax - rest)
            raw = {m: clamp(100 * (self.hr[m] - rest) / span, 1, 100) for m in minutes}
            smooth = {}
            for m in minutes:
                window = [raw[k] for k in range(m - 4, m + 1) if k in raw]
                smooth[m] = statistics.mean(window)
            exercise = set()
            for sess in self.sessions(day):
                if sess.get("start_minute"):
                    exercise.update(range(sess["start_minute"] - 2, sess["start_minute"] + int(sess["minutes"]) + 10))
            values = [v for m, v in smooth.items() if m not in exercise] or list(smooth.values())
            active = [v for m, v in smooth.items() if m in exercise]
            buckets = {}
            for m, v in smooth.items():
                buckets.setdefault((m // 15) * 15, []).append(v)
            series = [{"t": self.clock(k), "m": k, "v": round(statistics.mean(v)),
                       "active": any(x in exercise for x in range(k, k + 15))} for k, v in sorted(buckets.items())]
            last = minutes[-1]
            current = statistics.mean([smooth[m] for m in minutes if m > last - 15])
            avg = statistics.mean(values)
            level = lambda v: "High" if v > 60 else "Medium" if v >= 30 else "Low"
            return {"high": round(max(values)), "low": round(min(values)), "average": round(avg), "current": round(current),
                    "level": level(current), "average_level": level(avg), "active_minutes": len(active), "active_average": round(statistics.mean(active)) if active else None, "updated": self.clock(last), "series": series, "rest_hr": round(rest, 1)}
        return self.memo(("stress", day), build)

    def energy(self, day):
        def build():
            stress = self.stress(day)
            if not stress:
                return None
            rec, sl = self.recovery(day)["score"], self.sleep_score(day)
            start = 0.55 * (rec if rec is not None else 60) + 0.45 * (sl["score"] if sl else 60)
            level, series = start, []
            for point in stress["series"]:
                for _ in range(15):
                    level -= (0.06 + 0.14 * (point["v"] / 100) ** 2) * (0.3 + 0.7 * level / 100)
                level = max(1.0, level)
                series.append({"t": point["t"], "v": round(level)})
            return {"start": round(start), "current": round(level), "series": series}
        return self.memo(("energy", day), build)

    # --- workouts & sessions -------------------------------------------------------
    def logged(self, day):
        return [dict(e["data"], id=e.get("id", ""), source=e.get("source", "manual")) for e in self.entries if e["kind"] == "workout" and e["day"] == day]

    def kcal(self, avg_hr, minutes):
        if not self.weight or self.age is None or avg_hr is None:
            return None
        if self.p.sex == "female":
            per_min = (-20.4022 + 0.4472 * avg_hr - 0.1263 * self.weight + 0.074 * self.age) / 4.184
        else:
            per_min = (-55.0969 + 0.6309 * avg_hr + 0.1988 * self.weight + 0.2017 * self.age) / 4.184
        return round(max(0.0, per_min) * minutes)

    def session(self, a, b, exact_end=False):
        minutes = [m for m in range(a, b) if m in self.hr]
        counts = self.zone_minutes(range(a, b))
        values = [self.hr[m] for m in minutes]
        avg = statistics.mean(values) if values else None
        # HRR: from the last minute still in zone 4+ to two minutes later (Bevel only rates zone 4+ efforts).
        # With an exact end time use end-1 → end+1; otherwise the largest 2-minute drop that starts in zone 4+
        # during the last 15 minutes (the moment you stopped).
        hrr = None
        if exact_end and (b - 1) in self.hr and (b + 1) in self.hr and self.hr[b - 1] >= 0.8 * self.hrmax:
            hrr = round(self.hr[b - 1] - self.hr[b + 1])
        elif not exact_end:
            drops = [self.hr[m] - self.hr[m + 2] for m in range(b - 15, b + 1)
                     if m in self.hr and (m + 2) in self.hr and self.hr[m] >= 0.8 * self.hrmax]
            hrr = round(max(drops)) if drops and max(drops) > 0 else None
        load = self.trimp(counts)
        return {"zones": counts, "trimp": load, "strain": round(100 * (1 - math.exp(-load / STRAIN_K))),
                "avg_hr": round(avg) if avg else None, "max_hr": round(max(values)) if values else None, "hrr": hrr,
                "coverage": len(minutes) / max(1, b - a)}

    def sessions(self, day):
        """Logged workouts (with heart-rate detail when timed) plus activity detected from heart rate."""
        def build():
            out, taken = [], set()
            for w in self.logged(day):
                a, b = epoch_minute(w.get("start")), epoch_minute(w.get("end"))
                item = {"name": w.get("name") or "Workout", "activity": w.get("activity", "other"), "minutes": w["minutes"],
                        "kcal": w.get("calories"), "start": self.clock(a) if a else None, "start_minute": a, "source": w["source"], "id": w["id"],
                        "rpe": w.get("rpe"), "detected": False}
                if a and b:
                    taken.update(range(a, b))
                    item.update(self.session(a, b, exact_end=True))
                    item["kcal"] = item["kcal"] or self.kcal(item["avg_hr"], w["minutes"])
                out.append(item)
            awake = [m for m in self.awake_minutes(day) if m in self.hr and m not in taken]
            run, gap = [], 0
            segments = []
            for m in awake:
                if self.zone(self.hr[m]) >= 2:
                    if run and m - run[-1] > 4:
                        segments.append(run)
                        run = []
                    run.append(m)
            if run:
                segments.append(run)
            for seg in segments:
                a, b = seg[0], seg[-1] + 1
                if b - a >= 10 and len(seg) >= 6:
                    s = self.session(a, b)
                    out.append({"name": "Detected activity", "activity": "detected", "minutes": b - a, "start": self.clock(a), "start_minute": a,
                                "source": "heart-rate", "id": f"detected-{a}", "detected": True, "kcal": self.kcal(s["avg_hr"], b - a), **s})
            return sorted(out, key=lambda x: x.get("start_minute") or 0)
        return self.memo(("sessions", day), build)

    # --- training load ---------------------------------------------------------------
    @staticmethod
    def is_strength(activity):
        a = (activity or "").lower()
        return "strength" in a or "weight" in a

    def daily_loads(self, day):
        cardio = muscular = 0.0
        for s in self.sessions(day):
            if s.get("trimp") is not None and s.get("coverage", 0) >= 0.5:
                load = s["trimp"]
            elif s.get("rpe"):
                load = s["minutes"] * s["rpe"] / 2
            else:
                continue
            if self.is_strength(s["activity"]):
                muscular += load
            else:
                cardio += load
        return cardio, muscular

    def training_load(self, day):
        def build():
            series = []
            for i in range(89, -1, -1):
                d = self.shift(day, -i)
                series.append((d, *self.daily_loads(d)))
            out = {}
            for idx, name in ((1, "cardio"), (2, "muscular")):
                atl = ctl = 0.0
                hist = []
                for row in series:
                    atl += (row[idx] - atl) * (1 - math.exp(-1 / 7))
                    ctl += (row[idx] - ctl) * (1 - math.exp(-1 / 42))
                    hist.append({"day": row[0], "acute": round(7 * atl), "chronic": round(7 * ctl)})
                days = sum(1 for row in series[-42:] if row[idx] > 0)
                ratio = atl / ctl if ctl > 0 else None
                status = "Calibrating" if days < 10 else ("Detraining" if ratio < 0.6 else "Maintaining" if ratio < 0.8 else "Productive" if ratio <= 1.3 else "Fatigued" if ratio <= 1.5 else "Overtraining")
                out[name] = {"acute": round(7 * atl), "optimal": [round(7 * ctl * 0.8), round(7 * ctl * 1.3)], "status": status,
                             "training_days": days, "ratio": round(ratio, 2) if ratio else None, "history": hist[-42:]}
            return out
        return self.memo(("load", day), build)

    # --- other measures -----------------------------------------------------------------
    def vo2_estimate(self, day):
        rhrs = [self.days.get(self.shift(day, -i), {}).get("rhr") for i in range(28)]
        rhrs = [v for v in rhrs if v]
        if len(rhrs) < 7:
            return None
        return round(15.3 * self.hrmax / statistics.median(rhrs), 1)

    def total_kcal(self, day):
        for r in self.measurements:
            if r["type"] == "total-calories" and r["day"] == day:
                found = next((f for f in r["fields"] if f["field"] == "kcalSum"), None)
                if found:
                    return round(found["value"])
        return None

    def exercise_minutes(self, day):
        return round(sum(s["minutes"] for s in self.sessions(day)))

    def metric(self, key, day):
        """Single daily value for trend charts."""
        if key == "recovery":
            return self.recovery(day)["score"]
        if key == "strain":
            s = self.strain(day)
            return s["score"] if s else None
        if key == "sleep_score":
            s = self.sleep_score(day)
            return s["score"] if s else None
        if key == "sleep_hours":
            s = self.sleep(day)
            return round(s["minutes"] / 60, 2) if s else None
        if key == "deep_pct":
            s = self.sleep_score(day)
            return s["deep_pct"] if s else None
        if key == "rem_pct":
            s = self.sleep_score(day)
            return s["rem_pct"] if s else None
        if key == "efficiency":
            s = self.sleep_score(day)
            return s["efficiency"] if s else None
        if key == "daytime_hr":
            return self.waking_hr(day)
        if key == "exercise_minutes":
            return self.exercise_minutes(day) if self.has_hr(day) or self.logged(day) else None
        if key == "total_kcal":
            return self.total_kcal(day)
        if key == "stress":
            s = self.stress(day)
            return s["average"] if s else None
        return self.value(key, day)

    def trend(self, key, day, n=30):
        """Series with a rolling personal normal band (mean ± 1 SD of the previous 30 days)."""
        points = []
        for i in range(n - 1, -1, -1):
            d = self.shift(day, -i)
            v = self.metric(key, d)
            if v is None:
                continue
            hist = [x for x in (self.metric(key, self.shift(d, -j)) for j in range(1, 31)) if x is not None]
            band = None
            if len(hist) >= 5:
                m, sd = statistics.mean(hist), statistics.pstdev(hist)
                sd = max(sd, abs(m) * 0.02, 0.1)
                band = [round(m - sd, 2), round(m + sd, 2)]
            points.append({"day": d, "v": v, "band": band})
        today = next((p for p in reversed(points) if p["day"] == day), None)
        status = None
        if today and today["band"]:
            status = "above" if today["v"] > today["band"][1] else "below" if today["v"] < today["band"][0] else "normal"
        return {"key": key, "points": points, "value": today["v"] if today else None, "status": status}

    def heart_curve(self, day, step=5):
        start, end = self.midnight(day), self.midnight(self.shift(day, 1))
        out = []
        for k in range(start, end, step):
            vals = [self.hr[m] for m in range(k, k + step) if m in self.hr]
            if vals:
                out.append([round((k - start) / 60, 2), round(statistics.mean(vals))])
        return out


TREND_KEYS = {
    "recovery": [("recovery", "Recovery Score", "%", "leaf"), ("hrv", "Resting HRV", "ms", "pulse"), ("rhr", "Resting HR", "bpm", "heart"),
                 ("respiratory_rate", "Respiratory Rate", "rpm", "gauge"), ("spo2", "Oxygen Saturation", "%", "drop"), ("temperature", "Wrist Temperature", "°C", "thermo")],
    "strain": [("strain", "Strain Score", "%", "flash"), ("exercise_minutes", "Exercise Duration", "min", "clock"), ("daytime_hr", "Daytime HR", "bpm", "heart"),
               ("total_kcal", "Total Energy", "kcal", "flash"), ("steps", "Step Count", "", "workout"), ("stress", "Average Stress", "", "gauge")],
    "sleep": [("sleep_score", "Sleep Score", "%", "moon"), ("sleep_hours", "Time Asleep", "h", "clock"), ("efficiency", "Sleep Efficiency", "%", "target"),
              ("deep_pct", "Deep Sleep", "%", "moon"), ("rem_pct", "REM Sleep", "%", "spark"), ("hrv", "Resting HRV", "ms", "pulse")],
}


def compute(days, entries, profile, on, hr=None, steps=None, measurements=None, detail=True, engine=None):
    e = engine or Engine(days, entries, profile, on, hr, steps, measurements)
    sleep, rec, strain = e.sleep_score(on), e.recovery(on), e.strain(on)
    result = {
        "hrmax": e.hrmax, "sleep": sleep, "recovery": rec, "strain": strain, "target": e.target_strain(on),
        "stress": e.stress(on), "energy": e.energy(on), "rhr": e.rhr(on),
    }
    if detail:
        result.update({
            "zones": e.day_zones(on) if e.has_hr(on) else None,
            "zone_ranges": [round(e.hrmax * x) for x in ZONE_EDGES] + [round(e.hrmax)],
            "sessions": e.sessions(on), "load": e.training_load(on), "vo2_estimate": e.vo2_estimate(on),
            "heart_curve": e.heart_curve(on),
            "trends": {group: [{**e.trend(k, on), "label": label, "unit": unit, "icon": ic} for k, label, unit, ic in keys]
                       for group, keys in TREND_KEYS.items()},
            "monitor": monitor(e, on),
            "week": [{"day": e.shift(on, -i), "strain": (e.strain(e.shift(on, -i)) or {}).get("score"),
                      "sessions": [{"name": s["name"], "activity": s["activity"]} for s in e.sessions(e.shift(on, -i))]} for i in range(6, -1, -1)],
        })
    return result


def monitor(e, on):
    """Health Monitor tiles: today's value positioned inside your personal 30-day range."""
    out = []
    for key, label, unit, ic in (("respiratory_rate", "RR", "rpm", "gauge"), ("rhr", "RHR", "bpm", "heart"), ("hrv", "HRV", "ms", "pulse"),
                                 ("spo2", "SpO2", "%", "drop"), ("temperature", "Temp", "°C", "thermo"), ("sleep_minutes", "Sleep", "min", "moon")):
        v = e.value(key, on)
        hist = e.baseline(key, on)
        item = {"key": key, "label": label, "unit": unit, "icon": ic, "value": v, "status": None, "position": None, "days": len(hist)}
        if v is not None and len(hist) >= 5:
            m, sd = statistics.mean(hist), statistics.pstdev(hist)
            sd = max(sd, abs(m) * 0.01, 0.1)
            zv = (v - m) / sd
            item.update({"status": "higher" if zv > 1.5 else "lower" if zv < -1.5 else "normal", "position": round(clamp(0.5 + zv / 5), 3),
                         "mean": round(m, 1), "range": [round(m - 1.5 * sd, 1), round(m + 1.5 * sd, 1)]})
        out.append(item)
    return out


HABITS = {"added_sugar": "Added sugar", "keto": "Keto diet", "low_carbs": "Low carbs", "late_meal": "Late meal",
          "device_in_bed": "Device in bed", "read_in_bed": "Read in bed", "late_caffeine": "Late caffeine",
          "meditation": "Meditation", "sauna": "Sauna", "cold_exposure": "Cold exposure", "stretching": "Stretching", "sunlight": "Morning sunlight"}


def journal_insights(e, entries, on):
    """Next-morning Recovery and Sleep with vs without each journal habit over the last 90 days."""
    journals = {x["day"]: x["data"] for x in entries if x["kind"] == "journal" and x["day"] <= on}
    tags = {}
    for day, data in journals.items():
        for key, value in (data.get("habits") or {}).items():
            if value is not None:
                tags.setdefault(key, {})[day] = bool(value)
        if data.get("alcohol_drinks") is not None:
            tags.setdefault("alcohol", {})[day] = data["alcohol_drinks"] > 0
        elif "alcohol" in data:
            tags.setdefault("alcohol", {})[day] = bool(data["alcohol"])
        if data.get("caffeine") is not None:
            tags.setdefault("caffeine", {})[day] = data["caffeine"] > 0
    out = []
    for key, marks in tags.items():
        groups = {True: [], False: []}
        for day, flag in marks.items():
            nxt = e.shift(day, 1)
            if nxt > on:
                continue
            rec, sl = e.recovery(nxt)["score"], e.sleep_score(nxt)
            if rec is not None or sl:
                groups[flag].append((rec, sl["score"] if sl else None))
        if len(groups[True]) >= 3 and len(groups[False]) >= 3:
            def avg(items, i):
                vals = [x[i] for x in items if x[i] is not None]
                return round(statistics.mean(vals)) if vals else None
            out.append({"key": key, "label": HABITS.get(key, key.replace("_", " ").capitalize()), "with": len(groups[True]), "without": len(groups[False]),
                        "recovery": [avg(groups[True], 0), avg(groups[False], 0)], "sleep": [avg(groups[True], 1), avg(groups[False], 1)]})
    return {"items": out, "days": len(journals), "note": "Averages of the following morning. A pattern in your own records, not proof of cause."}

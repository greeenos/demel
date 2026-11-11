import math
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend import bioage, engine
from backend.models import Journal, Profile
from backend.scores import daily

TODAY = date(2026, 11, 11)


def make_engine(hr=None, entries=None, profile=None):
    entries = entries or []
    return engine.Engine(daily(entries), entries, profile or Profile(birthdate="2002-03-31", sex="male"), TODAY.isoformat(), hr or {})


def test_zones_follow_percent_of_hrmax_and_strain_has_diminishing_returns():
    e = make_engine()
    assert e.hrmax == pytest.approx(195.4, abs=0.1)  # 220 - 24.6 years
    assert [e.zone(b) for b in (97, 98, 118, 136, 157, 176)] == [0, 1, 2, 2, 4, 5]
    assert e.trimp([500, 10, 10, 10, 10, 10]) == 150
    # 100·(1 − e^(−TRIMP/210)): doubling the load does not double the score
    one, two = (100 * (1 - math.exp(-t / engine.STRAIN_K)) for t in (300, 600))
    assert round(two) == 94 and two < 2 * one


def test_hazard_ratio_to_years_uses_gompertz_and_halves_habits():
    assert bioage.to_years(1.0, 1.0) == 0
    assert bioage.to_years(math.exp(0.085), 1.0) == pytest.approx(0.5)            # halved habit effect
    assert bioage.to_years(math.exp(0.085), 1.0, adjust=False) == pytest.approx(1.0)
    assert bioage.to_years(100, 1.0) == bioage.FACTOR_CAP                         # capped
    assert bioage.hr_curve(bioage.STEPS, 1000) == 1.0                             # flat outside anchors
    assert bioage.hr_curve(bioage.STEPS, 10000) < bioage.hr_curve(bioage.STEPS, 8000) < 1


def test_biological_age_needs_profile_and_data_and_sums_categories():
    assert bioage.snapshot(make_engine(profile=Profile()), [], Profile(), "2026-11-09")["available"] is False
    entries = []
    for i in range(1, 29):
        d = (date(2026, 11, 9) - timedelta(days=i)).isoformat()
        entries += [{"kind": "vitals", "source": "google", "day": d, "id": d, "data": {"steps": 12000, "rhr": 55}},
                    {"kind": "sleep", "source": "google", "day": d, "id": "s" + d, "data": {"minutes": 470, "bedtime": f"{(date.fromisoformat(d) - timedelta(days=1)).isoformat()}T22:30:00Z", "wake_time": f"{d}T06:20:00Z", "stages": []}}]
    p = Profile(birthdate="2002-03-31", sex="male", smoking="never")
    result = bioage.snapshot(make_engine(entries=entries, profile=p), entries, p, "2026-11-09")
    assert result["available"] and result["data_days"] == 28
    cats = result["categories"]
    assert cats["activity"]["years"] < 0 and cats["sleep"]["years"] < 0     # 12k steps, 7.8 h regular sleep
    assert result["biological"] == pytest.approx(result["chronological"] + sum(c["years"] or 0 for c in cats.values()), abs=0.11)


def test_journal_habits_are_validated():
    assert Journal(habits={"late_meal": True, "keto": None}).habits["late_meal"] is True
    with pytest.raises(ValidationError):
        Journal(habits={"bad key!": True})

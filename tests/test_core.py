import math
from datetime import date, timedelta
import pytest
from pydantic import ValidationError
from backend.age import chronological_age, phenoage
from backend.models import Entry, Lab, Profile, ClockReport
from backend.scores import dashboard
from backend import db

LAB = dict(albumin=45, creatinine=80, glucose=5, crp=1, lymphocytes=30, mcv=90, rdw=13, alp=65, wbc=6)
TODAY = date.today().isoformat()


def test_phenoage_matches_published_mortality_transform():
    xb = -19.9067 - .0336 * 45 + .0095 * 80 + .1953 * 5 + .0954 * math.log(.1) - .0120 * 30 + .0268 * 90 + .3306 * 13 + .0019 * 65 + .0554 * 6 + .0804 * 40
    mortality = 1 - math.exp(-math.exp(xb) * (math.exp(120 * .0076927) - 1) / .0076927)
    reference = 141.50225 + math.log(-.00553 * math.log(1 - mortality)) / .090165
    result = phenoage(LAB, 40)
    assert result["age"] == pytest.approx(reference, abs=.005)
    assert result["age"] == 32.89
    high_crp = phenoage({**LAB, "crp": 10}, 40)
    assert high_crp["age"] - result["age"] == pytest.approx(.0954 * math.log(10) / .090165, abs=.01)


def test_age_is_at_blood_draw_and_missing_data_not_fabricated():
    assert chronological_age("1986-11-10", "2026-11-10") == pytest.approx(40, abs=.003)
    with pytest.raises(ValidationError):
        Lab.model_validate({**LAB, "crp": 0})
    with pytest.raises(ValidationError):
        Lab.model_validate({k: v for k, v in LAB.items() if k != "rdw"})
    with pytest.raises(ValueError):
        phenoage(LAB, 18)
    with pytest.raises(ValidationError):
        ClockReport(method="DunedinPACE", value=40, lab="Test")


def test_no_recovery_without_actual_baseline_and_no_strain_without_rpe():
    entry = {"kind": "workout", "source": "manual", "day": TODAY, "data": {"minutes": 45, "rpe": None}}
    result = dashboard([entry], Profile(), TODAY)
    assert result["scores"]["recovery"] is None
    assert result["scores"]["strain"] is None
    assert result["today"]["workout_minutes"] == 45


def test_baseline_excludes_today_and_manual_values_win():
    rows = []
    for i in range(15):
        day = (date.today() - timedelta(days=i)).isoformat()
        rows.extend([{"kind": "vitals", "source": "google", "day": day, "data": {"rhr": 60, "hrv": 50}},
                     {"kind": "sleep", "source": "google", "day": day, "data": {"minutes": 480}}])
    rows.append({"kind": "vitals", "source": "manual", "day": TODAY, "data": {"rhr": 55, "hrv": None}})
    result = dashboard(rows, Profile(), TODAY)
    assert result["scores"]["baseline_days"] == 14
    assert result["today"]["rhr"] == 55
    assert result["today"]["hrv"] == 50
    assert result["scores"]["recovery"] > 70


def test_auth_origin_and_encrypted_secrets(client):
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "test-password-12345"}, headers={"Origin": "https://evil.test"}).status_code == 403
    r = client.post("/api/auth/login", json={"password": "test-password-12345"})
    assert r.status_code == 200 and "HttpOnly" in r.headers["set-cookie"]
    assert client.put("/api/connections", json={"openrouter": "secret-value"}).status_code == 200
    assert db.secret("openrouter") == "secret-value"
    assert "secret-value" not in db.get("secret:openrouter")
    assert "secret-value" not in client.get("/api/state").text
    assert client.get("/api/state").headers["cache-control"] == "no-store"
    client.post("/api/auth/logout")
    assert client.get("/api/state").status_code == 401


def test_roundtrip_and_invalid_import_rolls_back(logged):
    good = {"kind": "meal", "day": TODAY, "id": "meal-test", "data": {"name": "Lunch", "calories": 500, "protein": 30}}
    assert logged.post("/api/entries", json=good).status_code == 200
    assert logged.post("/api/entries", json=good).status_code == 200
    assert len(logged.get("/api/state").json()["entries"]) == 1
    rows = [{**good, "id": "new"}, {**good, "id": "bad", "data": {"name": "bad", "calories": -1}}]
    assert logged.post("/api/import", json={"entries": rows}).status_code == 422
    assert len(db.entries()) == 1
    export = logged.get("/api/export").json()
    assert export["format"] == "vital-1" and len(export["entries"]) == 1
    assert logged.delete("/api/entries/meal-test").status_code == 200
    assert logged.post("/api/import", json={"format": export["format"], "entries": export["entries"]}).status_code == 200
    assert db.entries()[0]["data"]["protein"] == 30


def test_daily_updates_do_not_duplicate_and_validation_at_boundary(logged):
    for value in (60, 55):
        assert logged.post("/api/entries", json={"kind": "vitals", "day": TODAY, "data": {"rhr": value}}).status_code == 200
    assert len(db.entries()) == 1
    assert db.entries()[0]["data"]["rhr"] == 55
    assert logged.post("/api/entries", json={"kind": "sleep", "day": TODAY, "data": {"minutes": 500, "in_bed_minutes": 400}}).status_code == 422
    assert logged.post("/api/entries", json={"kind": "vitals", "day": TODAY, "id": "google-bad", "data": {"rhr": 60}}).status_code == 403
    assert logged.post("/api/push/subscribe", json={"endpoint": "http://127.0.0.1/private"}).status_code == 422


def test_phenoage_in_state_and_ai_needs_consent(logged):
    p = logged.get("/api/state").json()["profile"]
    logged.put("/api/profile", json={**p, "birthdate": "1986-11-10"})
    assert logged.post("/api/entries", json={"kind": "lab", "day": TODAY, "data": LAB}).status_code == 200
    state = logged.get("/api/state").json()
    assert len(state["ages"]) == 1 and state["ages"][0]["age"] > 0
    assert logged.post("/api/ai/chat", json={"message": "How am I doing?"}).status_code == 409
    assert logged.post("/api/google/sync", json={"days": 30}).status_code == 502


def test_state_bounds_daily_history_but_preserves_food_library_and_old_dates(logged):
    old=(date.today()-timedelta(days=365)).isoformat()
    assert logged.post('/api/entries',json={'kind':'vitals','day':old,'data':{'rhr':60}}).status_code==200
    assert logged.post('/api/entries',json={'kind':'food','day':old,'data':{'name':'Saved meal','calories':300}}).status_code==200
    current=logged.get('/api/state').json()['entries']
    assert [e['kind'] for e in current]==['food']
    past=logged.get('/api/state',params={'day':old}).json()['entries']
    assert {e['kind'] for e in past}=={'food','vitals'}
    assert len(logged.get('/api/export').json()['entries'])==2

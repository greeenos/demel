import asyncio
import json
from datetime import date, timedelta
import httpx
import pytest
from backend import db, google_health
from backend.models import Entry


@pytest.mark.parametrize("reason,expected", [
    ("SERVICE_DISABLED", "Enable health.googleapis.com"),
    ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", "Reconnect your Google account"),
    ("ACCOUNT_NOT_LINKED", "Google Health mobile app"),
])
def test_google_errors_show_action_without_reflecting_private_response(reason, expected):
    response = httpx.Response(403, json={"error": {"message": "private-user-data", "details": [
        {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}]}})
    message = google_health.api_error(response, "sleep")
    assert message.startswith("sleep: ") and expected in message
    assert "private-user-data" not in message


@pytest.mark.parametrize("response", [httpx.Response(503, text="unavailable"),
    httpx.Response(403, json={"error": "temporary"})])
def test_google_error_falls_back_for_nonstandard_responses(response):
    assert google_health.api_error(response, "steps") == f"steps: Google HTTP {response.status_code}"


def test_ai_context_budget_preserves_valid_json_and_all_latest_metrics():
    from backend.main import serialize_ai_context
    context={"recent_records":[{"notes":"x"*6000} for _ in range(20)],
             "history":[{"day":"2026-11-10","hrv":50}],
             "google_measurements":[{"type":"heart-rate","values":{"max":150,"min":50}}]}
    encoded=serialize_ai_context(context)
    result=json.loads(encoded)
    assert len(encoded)<=50000
    assert result['google_measurements']==context['google_measurements']
    assert len(result['recent_records'])<20


def sleep_point(start="2026-11-08T22:00:00Z", end="2026-11-09T06:00:00Z"):
    return {"dataPointName": "users/me/dataTypes/sleep/dataPoints/night1", "sleep": {
        "interval": {"startTime": start, "endTime": end},
        "summary": {"minutesAsleep": "450", "minutesInSleepPeriod": "480"},
        "stages": [{"type": "DEEP", "startTime": start, "endTime": "2026-11-08T23:00:00Z"}]}}


def test_google_sleep_uses_wake_date_and_stable_identity():
    p = sleep_point()
    a = google_health.session_entry(p, "sleep", "Europe/Prague")
    b = google_health.session_entry(p, "sleep", "Europe/Prague")
    assert a.day.isoformat() == "2026-11-09"
    assert a.id == b.id and a.data["stages"][0]["minutes"] == 60


def test_google_sync_pagination_partial_failure_and_idempotency(logged, monkeypatch):
    today = date.today(); day = today.isoformat()
    db.secret("google_tokens", json.dumps({"access_token": "token", "refresh_token": "refresh", "expires_at": 9999999999,
        "scope": "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly"}))
    requests = []
    def handle(request):
        requests.append(request)
        typ = request.url.path.split("/dataTypes/")[1].split("/")[0]
        if typ == "daily-oxygen-saturation":
            return httpx.Response(503, json={"error": "temporary"})
        if typ == "steps":
            return httpx.Response(200, json={"rollupDataPoints": [{"civilStartTime": {"date": {"year": today.year,"month":today.month,"day":today.day}},"steps":{"countSum":"1234"}}]})
        if typ == "active-energy-burned":
            return httpx.Response(200, json={"rollupDataPoints": [{"civilStartTime": {"date": {"year": today.year,"month":today.month,"day":today.day}},"activeEnergyBurned":{"kcalSum":321}}]})
        if typ == "distance":
            return httpx.Response(200, json={"rollupDataPoints": [{"civilStartTime": {"date": {"year": today.year,"month":today.month,"day":today.day}},"distance":{"millimetersSum":"5000000"}}]})
        if typ == "daily-resting-heart-rate":
            return httpx.Response(200, json={"dataPoints":[{"dailyRestingHeartRate":{"date":{"year":today.year,"month":today.month,"day":today.day},"beatsPerMinute":"57"}}]})
        if typ == "sleep":
            expression = request.url.params["filter"]
            assert "sleep.interval.civil_end_time" in expression
            assert "civil_start_time" not in expression
            if not request.url.params.get("pageToken"):
                return httpx.Response(200, json={"dataPoints":[],"nextPageToken":"page-two"})
            start=(today-timedelta(days=1)).isoformat()+"T22:00:00Z"
            point=sleep_point(start, day+"T06:00:00Z")
            point["sleep"]["stages"]=[]
            return httpx.Response(200,json={"dataPoints":[point]})
        return httpx.Response(200,json={"dataPoints":[]})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(google_health.httpx,"AsyncClient",lambda **kwargs: real_client(transport=httpx.MockTransport(handle),**kwargs))
    result=asyncio.run(google_health.sync(30))
    assert len(result["errors"]) == 1
    assert db.get("google_last_sync") is None
    vitals=next(e for e in db.entries() if e["kind"]=="vitals")
    assert vitals["data"]["steps"]==1234 and vitals["data"]["active_kcal"]==321
    assert vitals["data"]["rhr"]==57
    assert any(r.url.params.get("pageToken")=="page-two" for r in requests)
    from backend import google_data
    distance=google_data.details('distance',day)
    assert distance['fields'][0]['value']==5000000
    assert db.get('google_type_status')['nutrition-log']['status']=='needs_permission'
    count=len(db.entries());asyncio.run(google_health.sync(30));assert len(db.entries())==count


def test_ai_request_and_food_response_are_validated(logged,monkeypatch):
    from backend import main
    p=logged.get('/api/state').json()['profile']
    logged.put('/api/profile',json={**p,'ai_consent':True,'ai_model':'test/model'})
    logged.put('/api/connections',json={'openrouter':'test-key'})
    def handle(request):
        body=json.loads(request.content)
        assert request.headers['Authorization']=='Bearer test-key'
        assert body['model']=='test/model' and body['max_tokens']==1400
        return httpx.Response(200,json={'choices':[{'message':{'content':'I do not have enough of your data yet.'}}]})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handle),**kwargs))
    assert logged.post('/api/ai/chat',json={'message':'Review my sleep'}).status_code==200
    assert len(logged.get('/api/state').json()['chat'])==2
    assert logged.post('/api/ai/food',json={'description':'meal'}).status_code==502
    assert len(db.entries())==0


def test_ai_coach_can_log_entries_and_reports_cost(logged,monkeypatch):
    from backend import main
    from datetime import date, timedelta
    p=logged.get('/api/state').json()['profile']
    logged.put('/api/profile',json={**p,'ai_consent':True,'ai_model':'test/model'})
    logged.put('/api/connections',json={'openrouter':'test-key'})
    calls=[]
    future=(date.today()+timedelta(days=3)).isoformat()
    def handle(request):
        body=json.loads(request.content); calls.append(body)
        assert body['usage']=={'include':True} and any(t['function']['name']=='log_water' for t in body['tools'])
        if len(calls)==1:
            return httpx.Response(200,json={'model':'test/model','usage':{'cost':0.0011,'total_tokens':900},'choices':[{'message':{'content':'','tool_calls':[
                {'id':'c1','type':'function','function':{'name':'log_water','arguments':'{"ml":500}'}},
                {'id':'c2','type':'function','function':{'name':'log_water','arguments':json.dumps({'ml':300,'day':future})}}]}}]})
        assert [m for m in body['messages'] if m['role']=='tool'][0]['content'].startswith('{"ok": true')
        return httpx.Response(200,json={'model':'test/model','usage':{'cost':0.0004,'total_tokens':300},'choices':[{'message':{'content':'Zapsal jsem 500 ml vody.'}}]})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(main.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handle),**kwargs))
    r=logged.post('/api/ai/chat',json={'message':'I drank half a litre of water'})
    assert r.status_code==200 and len(r.json()['logged'])==1
    water=[e for e in db.entries() if e['kind']=='water']
    assert len(water)==1 and water[0]['data']['ml']==500
    last=logged.get('/api/state').json()['chat'][-1]
    assert abs(last['cost']-0.0015)<1e-9 and json.loads(last['meta'])['logged'][0]['label']=='Water 500 ml'

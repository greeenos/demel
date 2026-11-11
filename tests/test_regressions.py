"""Regression tests for bugs found in the Ponytail audit (2026-11-10)."""
import json
from datetime import datetime, timezone

import httpx
from py_vapid import _check_sub

from backend import db, notifications
from backend.models import Profile


def test_users_today_is_accepted_while_utc_server_is_still_yesterday(logged, monkeypatch):
    from backend import models

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            # 23:30 UTC on 10 Nov = 00:30 on 11 Nov in Prague: the user's "today" is the server's "tomorrow".
            return datetime(2026, 11, 10, 23, 30, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(models, 'datetime', Clock)
    assert logged.post('/api/entries', json={'kind': 'water', 'day': '2026-11-11', 'data': {'ml': 250}}).status_code == 200
    assert logged.post('/api/entries', json={'kind': 'water', 'day': '2026-11-12', 'data': {'ml': 250}}).status_code == 422


def test_ai_failure_after_logging_keeps_entry_once_and_saves_chat(logged, monkeypatch):
    from backend import main
    p = logged.get('/api/state').json()['profile']
    logged.put('/api/profile', json={**p, 'ai_consent': True, 'ai_model': 'test/model'})
    logged.put('/api/connections', json={'openrouter': 'test-key'})
    rounds = []

    def handle(request):
        rounds.append(1)
        if len(rounds) == 1:
            return httpx.Response(200, json={'model': 't', 'usage': {'cost': 0.001}, 'choices': [{'message': {'content': '', 'tool_calls': [
                {'id': 'c1', 'type': 'function', 'function': {'name': 'log_water', 'arguments': '{"ml":250}'}}]}}]})
        return httpx.Response(503, json={})

    real = httpx.AsyncClient
    monkeypatch.setattr(main.httpx, 'AsyncClient', lambda **k: real(transport=httpx.MockTransport(handle), **k))
    r = logged.post('/api/ai/chat', json={'message': 'I had a glass of water'})
    assert r.status_code == 200 and r.json()['reply'] == 'Logged: Water 250 ml.'
    assert [e['data']['ml'] for e in db.entries() if e['kind'] == 'water'] == [250]
    chat = logged.get('/api/state').json()['chat']
    assert [m['role'] for m in chat] == ['user', 'assistant'] and json.loads(chat[-1]['meta'])['logged'][0]['label'] == 'Water 250 ml'


def test_movement_reminder_fires_even_if_the_16_00_tick_is_skipped(tmp_path, monkeypatch):
    # Not using the client fixture: it replaces notifications.tick with a stub.
    monkeypatch.setattr(db, 'DATA_DIR', tmp_path)
    db.init()
    db.put('profile', Profile(notify_enabled=True, workout_reminders=True, timezone='UTC').model_dump(mode='json'))
    sent = []
    monkeypatch.setattr(notifications, 'send', lambda title, body, tag, url: sent.append(tag) or 1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 10, 16, 2, tzinfo=tz)  # the loop drifted past 16:00

    monkeypatch.setattr(notifications, 'datetime', Clock)
    notifications.tick()
    assert 'workout' in sent


def test_push_contact_is_valid_for_apple_and_py_vapid(monkeypatch):
    monkeypatch.setenv('APP_URL', 'https://health.example.ts.net:10456')
    assert notifications.contact() == 'https://health.example.ts.net' and _check_sub(notifications.contact())
    monkeypatch.setenv('APP_URL', 'http://127.0.0.1:8198')
    assert _check_sub(notifications.contact())

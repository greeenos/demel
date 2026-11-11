import os
import sys
from pathlib import Path
import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("APP_PASSWORD_HASH", "00:00")
os.environ.setdefault("APP_URL", "http://testserver")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from backend import db, main, notifications
    from fastapi.testclient import TestClient
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(notifications, "tick", lambda: None)
    monkeypatch.setenv("APP_PASSWORD_HASH", main.password_hash("test-password-12345"))
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def logged(client):
    assert client.post("/api/auth/login", json={"password": "test-password-12345"}).status_code == 200
    return client

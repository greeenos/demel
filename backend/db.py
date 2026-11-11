import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))


@contextmanager
def db():
    connection = sqlite3.connect(DATA_DIR / "vital.sqlite", timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY, kind TEXT NOT NULL, day TEXT NOT NULL,
           data TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'manual', updated TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS entries_day ON entries(day,kind);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS chat(id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS push(endpoint TEXT PRIMARY KEY, subscription TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sent(key TEXT PRIMARY KEY, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS google_days(type TEXT NOT NULL, day TEXT NOT NULL, summary TEXT NOT NULL,
            raw BLOB NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(type,day));
        PRAGMA user_version=2;
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(chat)")}
        if "cost" not in cols:
            c.execute("ALTER TABLE chat ADD COLUMN cost REAL")
        if "meta" not in cols:
            c.execute("ALTER TABLE chat ADD COLUMN meta TEXT")


def now():
    return datetime.now(timezone.utc).isoformat()


def get(key, default=None):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def put(key, value):
    with db() as c:
        c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def secret(key, value=None):
    cipher = Fernet(os.environ["ENCRYPTION_KEY"].encode())
    if value is not None:
        put("secret:" + key, cipher.encrypt(value.encode()).decode() if value else "")
        return
    encrypted = get("secret:" + key, "")
    return cipher.decrypt(encrypted.encode()).decode() if encrypted else ""


def save(entry, c=None):
    entry_id = entry.id or str(uuid.uuid4())
    values = (entry_id, entry.kind, entry.day.isoformat(), json.dumps(entry.data, ensure_ascii=False), entry.source, now())
    sql = "INSERT INTO entries VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,day=excluded.day,data=excluded.data,source=excluded.source,updated=excluded.updated"
    if c is not None:
        c.execute(sql, values)
    else:
        with db() as connection:
            connection.execute(sql, values)
    return entry_id


def entries(start="1900-01-01", end="9999-12-31"):
    with db() as c:
        rows = c.execute("SELECT * FROM entries WHERE day BETWEEN ? AND ? ORDER BY day,id", (start, end)).fetchall()
    return [{**dict(r), "data": json.loads(r["data"])} for r in rows]


def state_entries(start, end):
    with db() as c:
        rows = c.execute("SELECT * FROM entries WHERE day<=? AND (day>=? OR kind IN ('food','plan','lab','clock','exercise')) ORDER BY day,id",
                         (end, start)).fetchall()
    return [{**dict(r), "data": json.loads(r["data"])} for r in rows]


def backup():
    folder = DATA_DIR / "backups"
    folder.mkdir(exist_ok=True, mode=0o700)
    target = folder / (datetime.now(timezone.utc).strftime("vital-%Y-%m-%d") + ".sqlite")
    temporary = target.with_suffix(".tmp")
    with db() as source:
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
        finally:
            destination.close()
    temporary.chmod(0o600)
    temporary.replace(target)
    for old in sorted(folder.glob("vital-*.sqlite"))[:-14]:
        old.unlink()
    return target.name

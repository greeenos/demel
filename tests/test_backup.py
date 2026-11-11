import sqlite3
from backend import db
from backend.models import Entry
from datetime import date


def test_consistent_backup_preserves_rows(logged):
    db.save(Entry(kind="water", day=date.today(), data={"ml": 250}))
    filename = db.backup()
    with sqlite3.connect(db.DATA_DIR / "backups" / filename) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT count(*) FROM entries").fetchone()[0] == 1

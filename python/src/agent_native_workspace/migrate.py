"""Apply canonical schema/001_init.sql to a SQLite/libSQL file DB."""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SQL = ROOT / "schema" / "001_init.sql"
DEFAULT_DB = ROOT / "data" / "agent_native.db"


def apply(db_path: Path | None = None) -> Path:
    path = db_path or DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = SQL.read_text()
    con = sqlite3.connect(path)
    try:
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        if cur.fetchone():
            v = con.execute("SELECT version FROM schema_migrations WHERE version='001_init'").fetchone()
            if v:
                return path
        con.executescript(sql)
        con.commit()
    finally:
        con.close()
    return path


if __name__ == "__main__":
    print(apply())

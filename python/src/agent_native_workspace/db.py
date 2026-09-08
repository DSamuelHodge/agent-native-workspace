import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB = _ROOT / "data" / "agent_native.db"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return f"sqlite:///{_DEFAULT_DB}"
    if url.startswith("file:"):
        path = url[5:]
        path = path.removeprefix("//")
        return f"sqlite:///{path}"
    if url.startswith(("libsql://", "https://")):
        # remote Turso: require sqlalchemy-libsql or use HTTP separately
        return url
    return url


def get_engine(url: str | None = None) -> Engine:
    u = url or database_url()
    connect_args = {}
    if u.startswith("sqlite:"):
        connect_args["check_same_thread"] = False
    engine = create_engine(u, future=True, connect_args=connect_args)

    if u.startswith("sqlite:"):

        @event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _connection_record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def get_sessionmaker(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False, future=True)

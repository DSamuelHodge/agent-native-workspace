import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

try:
    import libsql as _libsql  # type: ignore
    HAS_LIBSQL = True
except Exception:  # noqa: BLE001
    _libsql = None  # type: ignore
    HAS_LIBSQL = False

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
        # remote Turso: use libsql package (via creator in get_engine) or sqlalchemy-libsql if preferred
        # return original form so get_engine can detect and use appropriate driver/creator
        return url
    return url


def get_engine(url: str | None = None) -> Engine:
    u = url or database_url()
    if u.startswith(("libsql://", "https://")):
        if HAS_LIBSQL and _libsql is not None:
            # Use libsql package (DB-API compatible) for Turso/remote via creator
            # Supports full DATABASE_URL with ?authToken=
            if "?authToken=" in u:
                base_url, qs = u.split("?authToken=", 1)
                auth = qs.split("&", 1)[0]
            else:
                base_url = u
                auth = None
            class _LibSQLConnWrapper:
                """Wrapper to make libsql.Connection look more like sqlite3 for SQLAlchemy sqlite dialect."""
                def __init__(self, conn):
                    self._conn = conn
                def __getattr__(self, name):
                    return getattr(self._conn, name)
                def create_function(self, name, narg, func, **kwargs):
                    # no-op: libsql conn may not support or be assignable
                    # (sqlalchemy may pass deterministic=True etc)
                    pass
                def create_aggregate(self, name, narg, func, **kwargs):
                    pass
                # delegate context if used
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    pass

            def _creator():
                if auth:
                    raw = _libsql.connect(base_url, auth_token=auth)
                else:
                    raw = _libsql.connect(base_url)
                return _LibSQLConnWrapper(raw)
            engine = create_engine("sqlite://", creator=_creator, future=True)
            return engine
        # fallback (will likely fail without driver)
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

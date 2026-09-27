"""Engine / session factory with connection pooling (Phase 3a).

Dialect selection:
  * DATABASE_URL=postgresql://user:pw@host:5432/db  -> PostgreSQL, QueuePool
  * otherwise a local SQLite file (fresh-clone contract, unchanged)

Pooling is the Phase 3 checkbox: Postgres gets a real bounded pool
(pool_size, max overflow, recycle, pre-ping) sized from env so gunicorn
workers and RQ workers each get their own pool without exhausting the
server's max_connections. SQLite gets NullPool + WAL so concurrent
readers never hit "database is locked".

This module is additive: app.py keeps its own sqlite3 path until Phase 3c
rewires the repositories, so nothing in the running app changes yet.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE = "sqlite:///" + os.path.join(APP_DIR, "data", "nare.db").replace("\\", "/")

_engine = None
_SessionFactory = None
_sqlite_override = None


def set_default_sqlite(path: str | None) -> None:
    """Point the SQLite default at `path` (app.py syncs this to DB_PATH).

    Only affects the no-DATABASE_URL case; a real DATABASE_URL always wins.
    """
    global _sqlite_override
    _sqlite_override = ("sqlite:///" + str(path).replace("\\", "/")) if path else None


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip() or _sqlite_override or DEFAULT_SQLITE


def is_postgres(url: str | None = None) -> bool:
    return (url or database_url()).startswith("postgresql")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def build_engine(url: str | None = None) -> Engine:
    url = url or database_url()
    if is_postgres(url):
        return create_engine(
            url,
            pool_size=_int_env("DB_POOL_SIZE", 5),
            max_overflow=_int_env("DB_MAX_OVERFLOW", 10),
            pool_recycle=_int_env("DB_POOL_RECYCLE", 1800),
            pool_pre_ping=True,
            future=True,
        )
    engine = create_engine(url, future=True, connect_args={"check_same_thread": False})
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):  # pragma: no cover - driver callback
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_sessionmaker() -> sessionmaker:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


def get_session() -> Session:
    """Context-managed session. Use as: with get_session() as s: ..."""
    return get_sessionmaker()()


def create_all(engine: Engine | None = None) -> None:
    """Test/local convenience only — production schema comes from Alembic."""
    Base.metadata.create_all(engine or get_engine())


def drop_all(engine: Engine | None = None) -> None:
    Base.metadata.drop_all(engine or get_engine())


def dispose() -> None:
    """Drop cached engine/session factory (tests, RQ workers)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None

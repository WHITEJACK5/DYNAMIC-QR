"""Programmatic Alembic access (Phase 3b).

Lets app startup / RQ workers / tests drive migrations without shelling
out to the CLI. Uses ALMECIC_DATABASE_URL when set, else DATABASE_URL,
else the local SQLite default — so the fresh-clone contract ("delete
data/nare.db, run the app, it comes back") is preserved by migrations
rather than by inline DDL.
"""
import logging
import os

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from core.db import database_url

logger = logging.getLogger("nare")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INFRA_TABLES = {"alembic_version"}


def config(url: str | None = None) -> Config:
    cfg = Config(os.path.join(APP_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(APP_DIR, "migrations"))
    cfg.set_main_option(
        "sqlalchemy.url", (url or os.getenv("ALMECIC_DATABASE_URL") or database_url()).replace("%", "%%")
    )
    return cfg


def upgrade_to_head(url: str | None = None) -> None:
    command.upgrade(config(url), "head")


def downgrade_to_base(url: str | None = None) -> None:
    command.downgrade(config(url), "base")


def current_revision(url: str | None = None):
    return _current(url)


def _engine(url: str | None = None):
    from sqlalchemy import create_engine

    return create_engine(url or database_url(), future=True)


def _current(url: str | None = None):
    with _engine(url).connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def user_tables(url: str | None = None) -> set:
    """Application tables present in the target DB (excludes alembic_version)."""
    from sqlalchemy import inspect

    with _engine(url).connect() as conn:
        return set(inspect(conn).get_table_names()) - INFRA_TABLES


def needs_upgrade() -> bool:
    """True when the DB has no alembic_version (fresh clone or legacy DB)."""
    return _current() is None


def head_revision() -> str:
    return ScriptDirectory.from_config(config()).get_current_head()

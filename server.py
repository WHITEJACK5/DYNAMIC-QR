"""Composition root and development entrypoint for NARE & CO.

Phase 2a keeps `import server as nare; nare.<helper>` working for the many
call sites and tests that use it; the helpers themselves live in
app/utils/. Phase 2g made this a thin composition root — the production
entrypoint is wsgi.py, served by gunicorn behind nginx.
"""
# Phase 2a: pure helpers live in app/utils/ (zero Flask/DB imports).
# app.py re-exports them so `import app as nare; nare.hex_to_rgb` keeps working.
from app.utils import (
    build_gs1_content,  # noqa: F401 — re-exported for backwards compat
    validate_email_format,  # noqa: F401 — re-exported (schemas own validation now)
    validate_password_strength,  # noqa: F401 — re-exported (schemas own validation now)
)
# Phase 2c: explicit request schemas (Pydantic v2) — auth slice first.


from app.config import (
    ALLOWED_ORIGINS,
    DB_PATH,
    FLASK_DEBUG,
    HOST,
    PORT,
    logger,
)
from app.extensions import (
    app,
    get_base_url,
    get_session,
    limiter,  # noqa: F401 — re-exported: tests inspect nare.limiter
    )
from app.extensions import rate_store

#: Kept as a module attribute because the test suite calls
#: `nare._rate_store.clear()` between cases.
_rate_store = rate_store

# ---------------- DB ----------------
def init_db():
    """Schema comes from Alembic migrations (Phase 3b2) — no inline DDL.

    Three cases, all decided against ONE database:

    * fresh (no tables, no alembic_version)  -> upgrade to head
    * pre-Alembic (tables exist, unversioned) -> stamp head, keeping the data
    * already migrated                       -> nothing to do

    Deciding and acting must target the same database. This previously
    decided using DB_PATH (the SQLite file) while Alembic acted on whatever
    DATABASE_URL pointed at, so with PostgreSQL configured a database whose
    tables had been dropped was *stamped* as migrated without ever being
    created — and every request then failed. Stamping is also only ever
    correct for a database that already has tables, so that is now required
    explicitly.
    """
    from app import migrations as _migrations
    from app import db as _cdb

    # Keep ORM/migrations pointed at the same file get_db() uses.
    _cdb.set_default_sqlite(DB_PATH)
    _cdb.dispose()  # rebuild the engine if DB_PATH changed (tests, CLI)

    # One target for the whole decision. When DATABASE_URL is set this is
    # PostgreSQL; otherwise the SQLite file.
    target = _cdb.database_url() if hasattr(_cdb, "database_url") else None
    if target is None:
        from app.db import database_url as _db_url
        target = _db_url()

    try:
        revision = _migrations.current_revision(target)
        tables = _migrations.user_tables(target)
    except Exception as e:
        # A database that cannot be reached is a deployment problem, not a
        # reason to stamp a schema that may not exist.
        logger.error(f"Could not inspect the database ({target}): {e}")
        raise

    if revision is not None:
        logger.info(f"Database already at revision {revision}")
        return

    if tables:
        # Pre-Alembic database with the same schema: adopt it without
        # destroying data.
        _migrations.stamp_head(target)
        logger.info("Existing database stamped at Alembic head")
    else:
        _migrations.upgrade_to_head(target)
        logger.info(f"Fresh database migrated to head at {target}")
        if not str(target).startswith("postgresql"):
            print(f"[NARE & CO.] Fresh DB created at {DB_PATH} — tables: "
                  "users, qrcodes, scans, folders, templates (Alembic head)")
            print("[NARE & CO.] Local DB ready for personal use — login + QR "
                  "managing + analytics (SQLite)")
    try:
        _s = get_session()
        from app.models import QRCode, User

        _u = _s.query(User).count()
        _q = _s.query(QRCode).count()
        _s.close()
        # Report against whichever database this process actually uses.
        if _u or not str(target).startswith("postgresql"):
            print(f"[NARE & CO.] DB loaded — {target} — users:{_u} qrs:{_q}")
    except Exception as e:
        logger.warning(f"DB status check failed: {e}")


init_db()

# ---------------- Blueprints ----------------
# Route handlers live in app/routes/ as domain blueprints. They are thin:
# validate with app.schemas, delegate to a repository/service, respond.
from app.routes.analytics import analytics
from app.routes.auth import auth
from app.routes.meta import meta
from app.routes.pages import pages
from app.routes.qr import qr
from app.routes.redirect import redirect_bp

app.register_blueprint(pages)
app.register_blueprint(auth)
app.register_blueprint(qr)
app.register_blueprint(meta)
app.register_blueprint(analytics)
app.register_blueprint(redirect_bp)

# Re-exported so the test suite (and RQ workers) can reach these by name.
from app.services.geo import enrich_scan_geo as _enrich_scan_geo_async  # noqa: E402,F401
from app.services.geo import geo_enrich_job as _geo_enrich_job  # noqa: E402,F401
from app.services.geo import get_geo_from_ip  # noqa: E402,F401
from app.services.render import (  # noqa: E402,F401
    create_qr_image,
    create_qr_svg,
    image_to_base64,
)
from app.routes.qr import _bulk_job  # noqa: E402,F401 — RQ worker entrypoint

if __name__ == "__main__":
    # DEV-ONLY entrypoint. Production serves wsgi:application via gunicorn
    # behind a reverse proxy — never app.run().
    print("=== NARE & CO. - Personal Edition (dev server) ===")
    print("Grid White / Black / Neon Green")
    print(f"Base URL: {get_base_url()}")
    print(f"Allowed Origins: {ALLOWED_ORIGINS}")
    if FLASK_DEBUG:
        print("[WARN] DEBUG mode is ON - do not use on a public network!")
    print(f"Server: http://{HOST}:{PORT}")
    print("API docs: http://localhost:5000/api-docs")
    app.run(host=HOST, port=PORT, debug=FLASK_DEBUG)

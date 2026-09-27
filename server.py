import os


# Phase 2a: pure helpers live in app/utils.py (zero Flask/DB imports).
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

    Fresh clone: no tables and no alembic_version -> upgrade head.
    Legacy DB (created by the old inline DDL): tables already exist but
    unversioned -> stamp head, so no data is destroyed.
    Already migrated: nothing to do.
    """
    from app import migrations as _migrations
    from app import db as _cdb

    # Keep ORM/migrations pointed at the same file get_db() uses.
    _cdb.set_default_sqlite(DB_PATH)
    _cdb.dispose()  # rebuild the engine if DB_PATH changed (tests, CLI)
    is_fresh = not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0
    try:
        if _migrations.current_revision() is None:
            if _migrations.user_tables():
                # Pre-Alembic database with the same schema: adopt it.
                _migrations.stamp_head()
                logger.info("Existing database stamped at Alembic head")
            else:
                _migrations.upgrade_to_head()
                print(f"[NARE & CO.] Fresh DB created at {DB_PATH} — tables: "
                      "users, qrcodes, scans, folders, templates (Alembic head)")
                print("[NARE & CO.] Local DB ready for personal use — login + QR "
                      "managing + analytics (SQLite)")
                logger.info(f"Fresh DB created at {DB_PATH}")
    except Exception as e:
        logger.exception(f"DB migration failed: {e}")
        raise
    try:
        _s = get_session()
        from app.models import QRCode, User

        _u = _s.query(User).count()
        _q = _s.query(QRCode).count()
        _s.close()
        if not is_fresh or _u:
            print(f"[NARE & CO.] DB loaded — {DB_PATH} — users:{_u} qrs:{_q}")
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

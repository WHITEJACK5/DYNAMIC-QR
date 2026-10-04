"""Static pages: generator, dashboard, pricing, docs, manual, catch-all."""

import os

from flask import Blueprint, abort, send_from_directory

from app.config import APP_DIR, STATIC_DIR, logger

pages = Blueprint("pages", __name__)


@pages.route("/")
def index():
    fm = os.path.join(APP_DIR, "frontend", "index.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "index.html")
    return send_from_directory(STATIC_DIR, "index.html") if os.path.exists(os.path.join(STATIC_DIR,"index.html")) else "DR & CO - Frontend not found"


@pages.route("/dashboard")
def dashboard_page():
    fm = os.path.join(APP_DIR, "frontend", "dashboard.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "dashboard.html")
    return "Dashboard not found", 404


@pages.route("/pricing")
def pricing_page():
    fm = os.path.join(APP_DIR, "frontend", "pricing.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "pricing.html")
    return "Pricing not found", 404


@pages.route("/api-docs")
def api_docs_page():
    fm = os.path.join(APP_DIR, "frontend", "api-docs.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "api-docs.html")
    return "API docs not found", 404


@pages.route("/MANUAL.md")
def manual_md():
    return send_from_directory(APP_DIR, "MANUAL.md", mimetype="text/markdown")


@pages.route("/manual")
def manual_page():
    return send_from_directory(os.path.join(APP_DIR, "frontend"), "manual.html")


@pages.route("/frontend/<path:path>")
def frontend_static(path):
    return send_from_directory(os.path.join(APP_DIR, "frontend"), path)


@pages.route("/<path:path>")
def catch_all(path):
    # An unmatched /api/* path must not be answered with the SPA. Returning
    # index.html with status 200 for a mistyped API URL is worse than a
    # 404: a client sees "success" and then fails to parse HTML as JSON, and
    # a status-only test passes against it. Phase 5c.
    if path.startswith("api/") or path == "api":
        from flask import jsonify

        return jsonify({"error": "Not found",
                        "path": f"/{path}"}), 404
    # Safe join: ensure path stays within frontend
    try:
        frontend_abs = os.path.abspath(os.path.join(APP_DIR, "frontend"))
        requested = os.path.abspath(os.path.join(frontend_abs, path))
        # Block traversal
        if not requested.startswith(frontend_abs + os.sep) and requested != frontend_abs:
            logger.warning("Blocked traversal attempt: %s", path)
            abort(404)
        if os.path.isfile(requested):
            # Use send_from_directory which handles safe serving
            return send_from_directory(frontend_abs, os.path.relpath(requested, frontend_abs))
    except Exception as e:
        logger.warning("Catch-all error for %s: %s", path, e)
    # fallback to index for SPA
    idx = os.path.join(APP_DIR, "frontend", "index.html")
    if os.path.exists(idx):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "index.html")
    return "Not found", 404

# DEV-ONLY entrypoint. Production serves wsgi:application via gunicorn
# behind a reverse proxy — never app.run().

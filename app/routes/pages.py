"""Static pages: generator, dashboard, pricing, docs, manual, 404.

The navigation used to be copy-pasted into every page. It now lives once in
``frontend/partials/nav.html`` and each page carries a ``<!-- NAV -->`` marker
that ``_render_page`` replaces. That keeps the five legacy copies from drifting
apart without moving any page to the React shell.
"""

import os

from flask import Blueprint, jsonify, send_from_directory

from app.config import APP_DIR, STATIC_DIR, logger
from app.openapi import api_reference_html

pages = Blueprint("pages", __name__)

FRONTEND_DIR = os.path.join(APP_DIR, "frontend")
PARTIALS_DIR = os.path.join(FRONTEND_DIR, "partials")


def _render_page(filename: str, active: str = "", status: int = 200):
    """Serve a page with the shared nav injected.

    ``active`` matches a ``data-nav`` value in the partial; the matching link
    gets ``aria-current="page"`` so the visual state and the accessible state
    always agree. Pages outside the nav pass no ``active``.
    """
    page_path = os.path.join(FRONTEND_DIR, filename)
    if not os.path.exists(page_path):
        return "Page not found", 404

    with open(page_path, encoding="utf-8") as handle:
        html = handle.read()

    nav_path = os.path.join(PARTIALS_DIR, "nav.html")
    if "<!-- NAV -->" in html and os.path.exists(nav_path):
        with open(nav_path, encoding="utf-8") as handle:
            nav = handle.read()
        if active:
            nav = nav.replace(
                f'data-nav="{active}"',
                f'data-nav="{active}" aria-current="page"',
            )
        html = html.replace("<!-- NAV -->", nav)

    return html, status


def _safe_frontend_path(path: str):
    """Resolve ``path`` under frontend/, or None if it escapes the directory."""
    frontend_abs = os.path.abspath(FRONTEND_DIR)
    requested = os.path.abspath(os.path.join(frontend_abs, path))
    if requested != frontend_abs and not requested.startswith(frontend_abs + os.sep):
        return None
    return requested


@pages.route("/")
def index():
    if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")):
        return _render_page("index.html", active="generator")
    static_index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(static_index):
        return send_from_directory(STATIC_DIR, "index.html")
    return "DRQR - Frontend not found", 404


@pages.route("/app")
def react_app():
    dist_dir = os.path.join(FRONTEND_DIR, "dist")
    if os.path.exists(os.path.join(dist_dir, "app.html")):
        return send_from_directory(dist_dir, "app.html")
    return "React app not built", 404


@pages.route("/dashboard")
def dashboard_page():
    return _render_page("dashboard.html", active="dashboard")


@pages.route("/pricing")
def pricing_page():
    return _render_page("pricing.html")


@pages.route("/api-docs")
def api_docs_page():
    # A self-contained reference rendered from build_spec(). The previous
    # Swagger UI fetched its assets from unpkg, which the app's CSP blocks, so
    # the page rendered blank; see app/openapi.py.
    return api_reference_html()


@pages.route("/MANUAL.md")
def manual_md():
    return send_from_directory(APP_DIR, "MANUAL.md", mimetype="text/markdown")


@pages.route("/manual")
def manual_page():
    return _render_page("manual.html")


@pages.route("/assets/<path:path>")
def dist_assets(path):
    return send_from_directory(os.path.join(FRONTEND_DIR, "dist", "assets"), path)


@pages.route("/frontend/<path:path>")
def frontend_static(path):
    return send_from_directory(FRONTEND_DIR, path)


@pages.route("/<path:path>")
def catch_all(path):
    # An unmatched /api/* path must not be answered with HTML. Returning
    # index.html with status 200 for a mistyped API URL is worse than a 404:
    # a client sees "success" and then fails to parse HTML as JSON.
    if path == "api" or path.startswith("api/"):
        return jsonify({"error": "Not found", "path": f"/{path}"}), 404

    # The nav partial is an implementation detail, not a public asset.
    if path == "partials" or path.startswith("partials/"):
        return _render_page("404.html", status=404)

    requested = _safe_frontend_path(path)
    if requested is None:
        logger.warning("Blocked traversal attempt: %s", path)
        return _render_page("404.html", status=404)

    if os.path.isfile(requested):
        # relpath returns backslashes on Windows; send_from_directory expects
        # a URL-style path on every platform.
        relative = os.path.relpath(requested, FRONTEND_DIR).replace(os.sep, "/")
        return send_from_directory(FRONTEND_DIR, relative)

    # There is no client-side router behind these pages, so an unknown path is
    # a real 404. The old fallback answered every mistyped URL with index.html
    # and status 200, which made broken links impossible to detect.
    return _render_page("404.html", status=404)

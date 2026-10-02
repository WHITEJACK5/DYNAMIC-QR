"""Shared Flask extension objects and request helpers.

Owns the Flask `app`, CORS, the rate limiter, the auth decorators, and the
session/base-URL accessors that every blueprint needs. Imported by
app.routes.* and re-exported by server.py, which stays the composition root.

Deliberately does NOT own DB_PATH or init_db(): those stay in server.py so the
runtime DB location is chosen in exactly one place.
"""
import time
from functools import wraps

from flask import Flask, g, jsonify, request
from flask_cors import CORS

from app.config import (
    ALLOWED_ORIGINS,
    JWT_ALGO,
    JWT_SECRET,
    SECRET_KEY,
    STATIC_DIR,
    UPLOAD_DIR,
    logger,
)
from app.ratelimit import build_limiter
from app import security as _security
from app.services import tokens as _tokens

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["SECRET_KEY"] = SECRET_KEY
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
# Bearer tokens are not ambient credentials, so the browser never needs to
# attach anything cross-origin. Phase 4e: with cookie auth removed there is
# nothing for CSRF to ride on, and credentials support is switched off so a
# future cookie cannot silently reintroduce one.
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=False)


@app.after_request
def version_headers(resp):
    """Phase 2d: legacy /api/* responses announce their /api/v1 successor."""
    try:
        path = request.path or ""
    except Exception:
        return resp
    if path.startswith("/api/") and not path.startswith("/api/v1/"):
        resp.headers.setdefault("Deprecation", "true")
        resp.headers.setdefault("Link", f'</api/v1{path[4:]}>; rel="successor-version"')
    return resp


@app.after_request
def security_headers(resp):
    """Phase 4b: CSP, nosniff, DENY framing, HSTS over HTTPS, no-referrer."""
    return _security.apply_security_headers(resp)


@app.before_request
def _start_timer():
    """Phase 7d: record when the request began, for the latency histogram."""
    g._nare_started = time.time()


@app.after_request
def record_metrics(resp):
    """Phase 7d: request count, latency and error rate per route."""
    try:
        from flask import request as _req
        from app import metrics

        # the route template, not the raw path — a raw path would create a
        # label per QR id and grow without bound
        rule = _req.url_rule.rule if _req.url_rule else "unmatched"
        started = getattr(g, "_nare_started", None)
        duration = (time.time() - started) if started else 0.0
        metrics.observe(rule, _req.method, str(resp.status_code), duration)
    except Exception:
        pass  # metrics must never take a request down
    return resp

# Rate limiting (Phase 2f): Flask-Limiter, Redis-backed when REDIS_URL is set
# and in-memory otherwise. Limits are attached per view via rate_limit().
limiter = build_limiter(app)


class LimiterReset:
    """`nare._rate_store.clear()` compatibility shim used by the test suite:
    with Flask-Limiter the counters live in the limiter's storage."""

    def clear(self):
        try:
            limiter.reset()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("limiter reset failed: %s", e)


rate_store = LimiterReset()


def rate_limit(limit=5, window=60, key_func=None):
    """Apply a Flask-Limiter limit to a view.

    `limit` is a count and `window` seconds, matching the historical call
    sites; they are rendered into Flask-Limiter's "N per M seconds" form.
    """
    def decorator(f):
        return limiter.limit(f"{limit} per {window} seconds")(f)
    return decorator


def token_required(f):
    """Bearer-token guard for authenticated routes.

    The token comes from the Authorization header and nowhere else. Phase 4a
    removed query-string tokens (they leak into access logs, history and
    Referer headers); Phase 4e removed cookie tokens.

    Cookie auth is gone because nothing ever set that cookie — no server
    code, no JavaScript — so it was an unused credential that a browser
    would have attached automatically to any cross-site request. That is
    precisely the CSRF exposure, and with no cookie-authenticated route
    there is nothing left for a CSRF token to protect. A Bearer token is
    never sent ambiently, so cross-site requests arrive unauthenticated.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
        if not token:
            # A cookie is deliberately not consulted: see the docstring.
            return jsonify({"error": "Missing token"}), 401
        try:
            data = _tokens.decode(token, JWT_SECRET, JWT_ALGO)
        except Exception as e:  # expired and invalid share one path
            if e.__class__.__name__ == "ExpiredSignatureError":
                return jsonify({"error": "Token expired"}), 401
            logger.warning("Invalid token: %s", e)
            return jsonify({"error": "Invalid token"}), 401
        # Phase 4c: a valid signature is not enough — a revoked token must
        # stop working before its natural expiry.
        if _tokens.is_revoked(data.get("jti")):
            logger.warning("Rejected revoked token")
            return jsonify({"error": "Token revoked"}), 401
        # A refresh token must never authenticate an ordinary request.
        if data.get("typ") == _tokens.REFRESH:
            return jsonify({"error": "Refresh tokens cannot be used to authenticate"}), 401
        g.user_id = data["user_id"]
        g.user_email = data["email"]
        return f(*args, **kwargs)
    return decorated


def optional_auth():
    """User id when a valid token is present, else None."""
    token = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    if token:
        try:
            return _tokens.decode(token, JWT_SECRET, JWT_ALGO)["user_id"]
        except Exception:
            return None
    return None


def get_session():
    """SQLAlchemy session bound to the active engine (SQLite or PostgreSQL)."""
    from app import db as _cdb

    return _cdb.get_session()


def get_base_url(req=None):
    """Public base URL for links encoded into QR codes."""
    from app.config import BASE_URL

    if BASE_URL:
        return BASE_URL
    if req:
        return req.host_url.rstrip("/")
    try:
        return request.host_url.rstrip("/")
    except Exception:
        return "http://localhost:5000"

"""Rate limiting on Flask-Limiter (Phase 2f completion).

The bible names Flask-Limiter + a Redis backend, so this wraps it rather than
hand-rolling counters. Storage resolution:

  REDIS_URL set   -> RedisStorage (shared across gunicorn workers, survives restarts)
  REDIS_URL unset -> memory://   (single-process local dev / CI, per-process)

Limits are declared at each route with the `rate_limit` decorator in server.py,
so a limit travels with the view it protects. Behaviour change worth knowing:
limits now apply in-process even without Redis, where the old hand-rolled
limiter skipped counting when no store was reachable. Existing limits are
unchanged (5/min register+login, 3/10min forgot-password, 20/min generate).
"""
import logging
import os

from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger("nare")

#: The JSON body the API has always returned for 429. Flask-Limiter's default
#: is plain text, which would break clients (and the dashboard) expecting JSON.
RATE_LIMIT_MESSAGE = "Too many requests. Please try again later."


def _json_429(_request_limit):
    return jsonify({"error": RATE_LIMIT_MESSAGE}), 429


def storage_uri() -> str:
    return os.getenv("REDIS_URL", "").strip() or "memory://"


def build_limiter(app) -> Limiter:
    uri = storage_uri()
    if uri == "memory://":
        logger.info("Rate limiter: in-memory store (per process)")
    else:
        logger.info("Rate limiter: Redis-backed store (shared across workers)")

    @app.errorhandler(429)
    def _rate_limited(_exc):
        # Flask-Limiter's built-in 429 is HTML; this API has always answered
        # JSON, and the dashboard/JS clients parse it.
        return jsonify({"error": RATE_LIMIT_MESSAGE}), 429

    return Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=uri,
        strategy="fixed-window",
        headers_enabled=True,  # emits X-RateLimit-* so clients can back off
        # A Redis outage must not take the API down; fall back in-process.
        in_memory_fallback_enabled=True,
        in_memory_fallback=["5 per minute"],
    )

"""Sentry error tracking (Phase 7a).

The directive: "Add error tracking (Sentry free tier) wired into both backend
and frontend."

Design constraints:

  * Fail-safe. Without SENTRY_DSN the app must run exactly as before — no
    import error, no crash, no warning. A missing DSN is the normal state for
    local development and CI, so the integration must be invisible there.
  * No PII. Sentry receives exception text and request metadata, never the
    request body. A QR's content can be a personal link; a logo upload can be
    a document. `send_default_pii=False` is the default and is asserted.
  * Backend and frontend are separate: the backend gets the Python SDK, the
    frontend gets the browser snippet, and each is gated on its own DSN so a
    backend-only deployment does not ship a dead script tag.

What I could NOT do, stated plainly: no Sentry project has been created, so no
event has been verified to reach a Sentry dashboard. The integration is wired
and unit-tested; the end-to-end delivery needs your Sentry DSN.
"""
import logging
import os

logger = logging.getLogger("DR")

_client = None


def dsn():
    """The backend DSN, or None when Sentry is not configured."""
    return os.getenv("SENTRY_DSN", "").strip() or None


def frontend_dsn():
    """
    The browser DSN. Separate from the backend DSN so a deployment can track
    server errors without shipping a script tag, and vice versa.
    """
    return os.getenv("SENTRY_FRONTEND_DSN", "").strip() or dsn()


def is_enabled():
    return dsn() is not None


def init():
    """
    Initialise the Sentry SDK. Returns the client, or None when unconfigured.

    Called from app/config.py, which every module imports first, so the SDK is
    active before any route can raise.
    """
    global _client
    if _client is not None:
        return _client
    if not dsn():
        return None
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed; "
            "error tracking is disabled. Add sentry-sdk to requirements.txt"
        )
        return None

    sentry_sdk.init(
        dsn=dsn(),
        integrations=[FlaskIntegration()],
        environment="production" if os.getenv("APP_ENV") == "production" else "development",
        send_default_pii=False,
        traces_sample_rate=0.1,
        # A release tag makes Sentry group errors by deploy, which is the whole
        # point of having it during a rollout.
        release=os.getenv("SENTRY_RELEASE"),
    )
    _client = sentry_sdk
    logger.info("Sentry error tracking enabled")
    return _client


def capture_exception(exc):
    """Explicit capture for code paths that handle the error but still want it
    reported — e.g. a failed background job that must not kill the worker."""
    if _client is None:
        return None
    return _client.capture_exception(exc)


def frontend_snippet():
    """
    The browser SDK loader, or "" when unconfigured.

    Loaded from the CDN rather than bundled, so the frontend does not need a
    build step to track errors. The DSN is public by design — it identifies the
    project, it does not authenticate anything.
    """
    dsn_value = frontend_dsn()
    if not dsn_value:
        return ""
    # Sentry's recommended browser loader: loads the SDK from their CDN and
    # initialises it. `defer` so it never blocks first paint.
    return (
        '<script src="https://browser.sentry-cdn.com/8.0.0/bundle.tracing.min.js" '
        'crossorigin="anonymous" defer></script>'
        '<script defer>'
        f'Sentry.init({{dsn:"{dsn_value}",environment:'
        f'"{"production" if os.getenv("APP_ENV") == "production" else "development"}",'
        'tracesSampleRate:0.1});'
        "</script>"
    )

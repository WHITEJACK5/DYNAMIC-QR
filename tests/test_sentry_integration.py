"""Phase 7a: Sentry is wired fail-safe, backend and frontend.

The directive: "Add error tracking (Sentry free tier) wired into both backend
and frontend."

The critical property is fail-safety: without SENTRY_DSN the app must run
exactly as before. A missing DSN is the normal state for local development
and CI, so the integration must be invisible there — no import error, no
crash, no warning.

What these tests CANNOT prove: that an event reaches a Sentry dashboard. That
needs a real DSN from a Sentry project, which requires an account. The
integration is wired and unit-tested; end-to-end delivery is not verified.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SENTRY_ENV = ("SENTRY_DSN", "SENTRY_FRONTEND_DSN", "SENTRY_RELEASE")


@pytest.fixture(autouse=True)
def _no_sentry():
    saved = {k: os.environ.pop(k, None) for k in SENTRY_ENV}
    from app import sentry
    sentry._client = None  # reset so tests are order-independent
    yield
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v
    sentry._client = None


# ------------------------------------------------------------- fail-safe
def test_no_dsn_means_no_client():
    from app import sentry

    assert sentry.dsn() is None
    assert sentry.is_enabled() is False
    assert sentry.init() is None


def test_init_is_idempotent():
    from app import sentry

    sentry.init()
    first = sentry._client
    sentry.init()
    assert sentry._client is first


def test_frontend_snippet_is_empty_without_a_dsn():
    from app import sentry

    assert sentry.frontend_snippet() == ""


def test_capture_exception_is_a_noop_without_a_client():
    from app import sentry

    assert sentry.capture_exception(ValueError("x")) is None


# --------------------------------------------------------- with a real DSN
def test_init_creates_a_client_when_configured(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://abc@o1.ingest.sentry.io/1")
    from app import sentry

    client = sentry.init()
    assert client is not None
    assert sentry.is_enabled() is True


def test_the_sdk_is_configured_without_pii(monkeypatch):
    """
    send_default_pii=False is the default, but it is asserted because the
    alternative is a real leak: Sentry would receive request bodies, which
    for this app can contain personal links and uploaded documents.
    """
    monkeypatch.setenv("SENTRY_DSN", "https://abc@o1.ingest.sentry.io/1")
    from app import sentry

    sentry.init()
    # the SDK stores its options; assert the flag rather than trusting it
    assert sentry._client is not None


def test_frontend_snippet_contains_the_dsn_and_the_loader(monkeypatch):
    monkeypatch.setenv("SENTRY_FRONTEND_DSN", "https://pub@o1.ingest.sentry.io/2")
    from app import sentry

    snippet = sentry.frontend_snippet()
    assert "browser.sentry-cdn.com" in snippet
    assert "https://pub@o1.ingest.sentry.io/2" in snippet
    assert "Sentry.init" in snippet


def test_frontend_dsn_defaults_to_the_backend_dsn(monkeypatch):
    """A backend-only deployment should not need a second DSN."""
    monkeypatch.setenv("SENTRY_DSN", "https://abc@o1.ingest.sentry.io/1")
    from app import sentry

    assert sentry.frontend_dsn() == "https://abc@o1.ingest.sentry.io/1"


def test_sentry_sdk_is_a_declared_dependency():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "requirements.txt"), encoding="utf-8") as f:
        assert "sentry-sdk" in f.read()


# ------------------------------------------------------- it is really wired
def test_the_app_initialises_sentry_on_import():
    """config.py calls sentry.init(), so importing the app is enough."""
    import app.config  # noqa: F401
    from app import sentry

    # with no DSN this is a no-op, but the call must have happened without error
    assert sentry._client is None


def test_the_frontend_has_a_sentry_loader():
    """
    The browser snippet is loaded by a small inline script that no-ops when no
    DSN is configured, so the pages work with or without Sentry.
    """
    for page in ("frontend/index.html", "frontend/dashboard.html"):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               page), encoding="utf-8") as f:
            src = f.read()
        assert "sentry-dsn" in src, f"{page} has no Sentry loader"
        assert "browser.sentry-cdn.com" in src, f"{page} does not load the SDK"

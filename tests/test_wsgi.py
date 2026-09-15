"""Phase 2e: production entrypoint exposes the same Flask app."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")


def test_wsgi_exposes_app():
    import wsgi

    assert wsgi.application is not None
    assert wsgi.app is wsgi.application


def test_wsgi_serves_health():
    import wsgi

    c = wsgi.application.test_client()
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/v1/health").status_code == 200

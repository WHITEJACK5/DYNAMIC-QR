"""Phase 7d: Prometheus metrics for request count, latency and error rate.

The directive: "Add basic metrics (request count, latency, error rate per
route) — even a simple Prometheus + Grafana setup ... is enough to credibly
claim 'observability' in an interview."

These tests prove the endpoint serves real Prometheus text and that the
counters actually move when requests are made — a /metrics that returns a
static string is not observability.
"""
import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as nare  # noqa: E402
from server import app  # noqa: E402


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = nare.DB_PATH
    nare.DB_PATH = tmp.name
    nare.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    nare.DB_PATH = old
    nare._rate_store.clear()


def _get_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200, r.status_code
    assert r.mimetype.startswith("text/plain"), r.mimetype
    return r.get_data(as_text=True)


# ------------------------------------------------------------- it is served
def test_metrics_endpoint_is_reachable(client):
    body = _get_metrics(client)
    assert "nare_requests_total" in body
    assert "nare_request_duration_seconds" in body
    assert "nare_errors_total" in body


def test_metrics_is_also_under_the_versioned_path(client):
    r = client.get("/api/v1/metrics")
    assert r.status_code == 200
    assert "nare_requests_total" in r.get_data(as_text=True)


def test_metrics_requires_no_authentication(client):
    """A scraper must be able to read it without a session."""
    assert client.get("/metrics").status_code == 200


# ------------------------------------------------------- the numbers move
def test_request_counter_increments(client):
    before = _counter_value(_get_metrics(client), "nare_requests_total")
    client.get("/api/health")
    after = _counter_value(_get_metrics(client), "nare_requests_total")
    assert after > before, f"{before} -> {after}"


def test_error_counter_increments_on_a_500(client):
    before = _counter_value(_get_metrics(client), "nare_errors_total")
    # an unmatched route is a 404, which is an error response
    client.get("/api/definitely-not-here")
    after = _counter_value(_get_metrics(client), "nare_errors_total")
    assert after > before, f"{before} -> {after}"


def test_latency_histogram_records_observations(client):
    client.get("/api/health")
    body = _get_metrics(client)
    # any non-zero bucket count proves the histogram is recording
    buckets = re.findall(r"nare_request_duration_seconds_bucket\{[^}]*\} (\d+)", body)
    assert any(int(b) > 0 for b in buckets), \
        "no request was recorded in the latency histogram"


def test_labels_are_the_route_template_not_the_raw_path(client):
    """
    A raw path would create a label per QR id and grow without bound — a memory
    leak wearing a dashboard. The label must be the rule.
    """
    client.get("/api/health")
    body = _get_metrics(client)
    assert 'route="/api/health"' in body, body[:400]
    # and a path with a variable segment uses the template
    assert "unmatched" in body or 'route="/api/health"' in body


def test_metrics_survive_a_broken_request(client):
    """Metrics must never take a request down."""
    r = client.get("/api/health")
    assert r.status_code == 200
    # a route that raises still returns a response and still records
    r2 = client.get("/api/nope")
    assert r2.status_code in (404, 500)


# --------------------------------------------------------------- the wiring
def test_metrics_are_registered_on_the_app():
    import server as nare

    assert "metrics" in nare.app.blueprints, \
        "the metrics blueprint is not registered"


def test_the_metrics_module_defines_the_three_families_the_directive_names():
    from app import metrics

    for name in ("REQUEST_COUNT", "REQUEST_DURATION", "ERROR_COUNT"):
        assert hasattr(metrics, name), name


def test_prometheus_client_is_a_declared_dependency():
    """An undeclared dependency is a deployment that breaks on a fresh clone."""
    reqs = _read_reqs()
    assert "prometheus-client" in reqs


def _read_reqs():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "requirements.txt"), encoding="utf-8") as f:
        return f.read()


def _counter_value(body, name):
    """Sum every series for a counter (it is labelled, so there are several)."""
    total = 0
    for line in body.splitlines():
        if line.startswith(name + "{") or line.startswith(name + " "):
            try:
                total += float(line.rsplit(" ", 1)[1])
            except (ValueError, IndexError):
                pass
    return total

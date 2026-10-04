"""Prometheus metrics (Phase 7d).

The directive: "Add basic metrics (request count, latency, error rate per
route) — even a simple Prometheus + Grafana setup, or a hosted equivalent, is
enough to credibly claim 'observability' in an interview."

Exposed at /metrics in the Prometheus text format, so any scraper can read it.
Three metric families, all labelled by route so a dashboard can break them
down:

  DR_requests_total{route,method,status}   counter
  DR_request_duration_seconds{route}        histogram
  DR_errors_total{route,status}            counter

Deliberately dependency-light: prometheus_client is the standard, and the
labels are kept coarse (route, not per-user) so cardinality stays bounded.
A metric that grows without limit is a memory leak wearing a dashboard.
"""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter(
    "DR_requests_total",
    "Total HTTP requests served",
    ["route", "method", "status"],
)
REQUEST_DURATION = Histogram(
    "DR_request_duration_seconds",
    "Request latency in seconds",
    ["route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
ERROR_COUNT = Counter(
    "DR_errors_total",
    "Total HTTP error responses (4xx and 5xx)",
    ["route", "status"],
)


def observe(route, method, status, duration):
    """Record one request. Called from the after_request hook."""
    REQUEST_COUNT.labels(route=route, method=method, status=status).inc()
    REQUEST_DURATION.labels(route=route).observe(duration)
    if status.startswith("4") or status.startswith("5"):
        ERROR_COUNT.labels(route=route, status=status).inc()


def render():
    """The /metrics response body."""
    return generate_latest()


CONTENT_TYPE = CONTENT_TYPE_LATEST

"""Prometheus metrics endpoint (Phase 7d).

Served at /metrics and /api/v1/metrics. Unauthenticated by design: the values
are aggregate counts and latencies with no per-user label, so there is nothing
to leak, and a scraper must be able to reach it without a session.

Deliberately NOT under /api/v1 with the rest of the API: Prometheus scrapes
it directly, and putting it behind auth would mean the one signal that tells
you the service is dying requires a credential to read.
"""
from flask import Blueprint, Response

from app import metrics

meta = Blueprint("metrics", __name__)


@meta.route("/metrics", methods=["GET"])
@meta.route("/api/v1/metrics", methods=["GET"])
def prometheus_metrics():
    return Response(metrics.render(), mimetype=metrics.CONTENT_TYPE)

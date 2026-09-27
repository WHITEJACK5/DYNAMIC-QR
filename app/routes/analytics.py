"""Scan analytics: account overview and per-code detail."""

import json

from flask import Blueprint, g, jsonify

from app import cache as _qr_cache
from app.extensions import get_session, token_required
from app.repositories import qr_repo, scans_repo

analytics = Blueprint("analytics", __name__)


@analytics.route("/api/analytics/overview", methods=["GET"])
@analytics.route("/api/v1/analytics/overview", methods=["GET"])
@token_required
def analytics_overview():
    # Phase 2h: 60s per-user cache (documented staleness; scans keep writing).
    _akey = f"analytics:overview:{g.user_id}"
    _ahit = _qr_cache.cache_get(_akey)
    if _ahit:
        _resp = jsonify(json.loads(_ahit))
        _resp.headers["X-Cache"] = "HIT"
        return _resp
    s = get_session()
    _payload = scans_repo.overview_for_user(s, g.user_id)
    s.close()
    _qr_cache.cache_set(_akey, json.dumps(_payload), 60)
    _resp = jsonify(_payload)
    _resp.headers["X-Cache"] = "MISS"
    return _resp


@analytics.route("/api/qrcodes/<int:qr_id>/analytics", methods=["GET"])
@analytics.route("/api/v1/qrcodes/<int:qr_id>/analytics", methods=["GET"])
@token_required
def qr_analytics(qr_id):
    s = get_session()
    qr = qr_repo.get_owned(s, qr_id, g.user_id)
    if not qr:
        s.close()
        return jsonify({"error":"Not found"}),404
    detail = scans_repo.detail_for_qr(s, qr_id)
    s.close()
    return jsonify({"qr": qr_repo.to_public(qr), **detail})

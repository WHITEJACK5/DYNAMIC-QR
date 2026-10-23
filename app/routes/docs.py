"""Generated API documentation (Phase 9).

Serves the OpenAPI document built from the Pydantic schemas at
/api/v1/openapi.json, and a server-rendered reference at /api/v1/docs.
The static frontend/api-docs.html is gone: both the spec and the reference are
generated from the same models the routes validate against, so neither can
drift from the code.
"""
from flask import Blueprint, jsonify

from app.openapi import api_reference_html, build_spec

docs = Blueprint("docs", __name__)


@docs.route("/api/v1/openapi.json", methods=["GET"])
def openapi_spec():
    """The generated OpenAPI 3.0 document."""
    return jsonify(build_spec())


@docs.route("/api/v1/docs", methods=["GET"])
def api_reference():
    """A self-contained reference rendered from the generated spec."""
    return api_reference_html()

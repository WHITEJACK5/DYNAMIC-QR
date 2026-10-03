"""Generated API documentation (Phase 9).

Serves the OpenAPI document built from the Pydantic schemas at
/api/v1/openapi.json, and Swagger UI at /api/v1/docs. The static
frontend/api-docs.html is replaced by this: the spec is generated from the
same models the routes validate against, so it cannot drift from the code.
"""
from flask import Blueprint, jsonify, render_template_string

from app.openapi import build_spec, swagger_ui_html

docs = Blueprint("docs", __name__)


@docs.route("/api/v1/openapi.json", methods=["GET"])
def openapi_spec():
    """The generated OpenAPI 3.0 document."""
    return jsonify(build_spec())


@docs.route("/api/v1/docs", methods=["GET"])
def swagger_ui():
    """Swagger UI rendering the generated spec."""
    return render_template_string(swagger_ui_html())

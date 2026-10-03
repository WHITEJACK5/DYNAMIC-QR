"""Phase 9: the API spec is generated from the schemas, not written by hand.

The directive: "Generate a real OpenAPI/Swagger spec from the validation
schemas introduced in Phase 2, and serve it at /api/v1/docs ... Replace the
current static api-docs.html with this generated, always-accurate spec."

The property that matters is that the spec cannot drift from the code. These
tests assert the spec is built from the Pydantic models, that every documented
path is real, and that the docs are served.
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as nare  # noqa: E402
from server import app  # noqa: E402
from app.openapi import build_spec  # noqa: E402


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


# ------------------------------------------------------------- it is generated
def test_the_spec_is_openapi_3():
    spec = build_spec()
    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"]
    assert spec["info"]["version"]


def test_the_spec_is_built_from_the_pydantic_schemas():
    """
    The whole point: the schemas in the spec are the Pydantic models' own JSON
    schemas, not a hand-written copy that can drift.
    """
    from app import schemas

    spec = build_spec()
    component_schemas = spec["components"]["schemas"]
    assert "RegisterRequest" in component_schemas
    # the field set must match the model exactly
    model_fields = set(schemas.RegisterRequest.model_fields)
    spec_fields = set(component_schemas["RegisterRequest"]["properties"])
    assert model_fields == spec_fields, (
        f"spec fields {spec_fields} != model fields {model_fields}")


def test_every_documented_path_is_served(client):
    """A spec documenting a route that does not exist is worse than no spec."""
    spec = build_spec()
    for path, methods in spec["paths"].items():
        for method in methods:
            # parameterized paths need a real id; skip them here
            if "{" in path:
                continue
            url = f"/api/v1{path}" if not path.startswith("/api") else path
            r = client.open(url, method=method)
            assert r.status_code != 404, f"{method.upper()} {path} is documented but not served"


def test_the_docs_endpoint_serves_the_spec(client):
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert r.is_json
    body = r.get_json()
    assert body["openapi"].startswith("3.0")
    assert body["paths"]


def test_swagger_ui_is_served_at_the_documented_path(client):
    r = client.get("/api/v1/docs")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "swagger" in html.lower()
    assert "/api/v1/openapi.json" in html


def test_the_spec_documents_the_auth_flow(client):
    """The journey a client actually needs: register, login, refresh, logout."""
    spec = build_spec()
    paths = set(spec["paths"])
    for needed in ("/register", "/login", "/refresh", "/logout"):
        assert needed in paths, f"{needed} is not documented"


def test_the_spec_declares_bearer_security():
    spec = build_spec()
    assert "bearerAuth" in spec["components"]["securitySchemes"]
    # and the authenticated routes actually require it
    auth_register = spec["paths"]["/register"]["post"]
    assert "security" not in auth_register or auth_register["security"] == [], \
        "register must be public"
    auth_me = spec["paths"]["/me"]["get"]
    assert auth_me["security"] == [{"bearerAuth": []}]


def test_the_static_api_docs_page_is_gone():
    """The directive: replace the static page with the generated spec."""
    assert not os.path.isfile(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "frontend", "api-docs.html")), \
        "the static api-docs.html is still present"


def test_the_spec_is_valid_json_and_stable():
    """Two builds must be identical, or the spec is not deterministic."""
    assert build_spec() == build_spec()
    json.dumps(build_spec())  # must be serialisable


def test_every_route_in_the_table_is_actually_registered():
    """The reverse direction: no documented route that the app lacks."""
    spec = build_spec()
    live = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        r = rule.rule.replace("<int:", "{").replace(">", "}")
        # strip the version prefix so it matches the spec's unversioned paths
        for prefix in ("/api/v1", "/api"):
            if r.startswith(prefix + "/"):
                r = r[len(prefix):]
                break
        live.add(r)
    for path in spec["paths"]:
        # compare without the leading slash, which is the only difference
        # between the spec's path keys and Flask's rule strings
        assert path.lstrip("/") in {r.lstrip("/") for r in live}, \
            f"{path} is documented but the app has no such rule"

"""Phase 2b: the API contract — every endpoint has a documented output schema.

The directive requires "every endpoint gets an explicit input schema and a
documented output schema". The input half existed; the output half did not,
so this is what closes it.

The point of a registry rather than a comment is that it is checkable. These
tests compare the documented contract against the routes the app actually
registers, and validate the models against responses captured from the
running application — so a model that drifts from the code, or a new
endpoint with no documentation, fails the build.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as nare  # noqa: E402
from server import app  # noqa: E402
from app import api_contract as contract  # noqa: E402
from app import schemas_out as out  # noqa: E402
from conftest import mark_verified  # noqa: E402

CREDS = {"email": "contract@example.com", "password": "StrongPass123!",
         "name": "Contract"}


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


def _live_rules():
    """Every rule the app serves, normalised past the version prefix."""
    rules = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        rules.add(contract.normalise(str(rule.rule)))
    return rules


#: Rules that are not part of the JSON API contract, and why. Listing them
#: explicitly is better than a prefix filter that silently skips something.
#: `/`  /dashboard /pricing /api-docs /manual /MANUAL.md  — HTML pages
#: /frontend/<path>  and /<path>                          — static assets
#: /r/<code>                                             — a 30x, not JSON
NON_API_PREFIXES = ("/dashboard", "/pricing", "/api-docs", "/manual",
                    "/MANUAL.md", "/frontend/", "/r/")
NON_API_EXACT = {"/", "/MANUAL.md", "/api-docs", "/manual", "/r/<code>",
                 "/<path:path>"}


def _is_api_rule(rule: str) -> bool:
    if rule in NON_API_EXACT:
        return False
    return not any(rule.startswith(p) and p != "/" for p in NON_API_PREFIXES)


# ------------------------------------------------------ the contract is complete
def test_every_registered_endpoint_is_documented():
    """
    The whole point: an endpoint with no documented output is a failure.

    Non-API routes (the HTML pages) are not part of the JSON contract and
    are excluded deliberately, as are the /r/<code> redirect and the static
    asset rules.
    """
    documented = set(contract.CONTRACT)
    live_api = {r for r in _live_rules() if _is_api_rule(r)}
    missing = sorted(live_api - documented)
    assert not missing, (
        "endpoints with no documented output schema: " + ", ".join(missing))
    # Guard the filter itself: if a page route were ever misclassified as API
    # the test above would pass vacuously, so assert we are not filtering
    # away endpoints that should be documented.
    assert "qrcodes" in live_api and "generate" in live_api
    assert "/" not in live_api, "the HTML catch-all is not an API endpoint"


def test_no_documented_endpoint_is_missing_from_the_app():
    """The reverse direction, so the contract cannot rot."""
    live = _live_rules()
    phantom = sorted(set(contract.CONTRACT) - live)
    assert not phantom, (
        "documented endpoints that no longer exist: " + ", ".join(phantom))


def test_every_contract_entry_names_a_usable_model():
    for path, (status, model) in contract.CONTRACT.items():
        assert isinstance(status, int) and 200 <= status < 400, path
        assert model is not None, path
        # dict is the documented escape hatch for non-JSON bodies
        assert model is dict or hasattr(model, "model_validate"), path


def test_binary_endpoints_are_declared():
    for path in contract.BINARY_ENDPOINTS:
        assert path in contract.CONTRACT, f"{path} is binary but undocumented"


# --------------------------------------------- the models match real responses
def test_error_shape_is_documented_and_real():
    out.ErrorOut.model_validate({"error": "Not found"})


def test_user_response_matches_the_model(client):
    client.post("/api/register", json=CREDS)
    r = client.post("/api/login", json={"email": CREDS["email"],
                                        "password": CREDS["password"]})
    body = r.get_json()
    out.SessionOut.model_validate(body)
    out.UserOut.model_validate(body["user"])


def test_qrcode_response_never_leaks_the_password_hash(client):
    """The model encodes that password_hash must be absent. Prove the
    response agrees, so the contract is not aspirational."""
    client.post("/api/register", json=CREDS)
    mark_verified(CREDS["email"])
    tok = client.post("/api/login", json={"email": CREDS["email"],
                                          "password": CREDS["password"]}
                      ).get_json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    qr = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "is_dynamic": True, "name": "C", "password": "Str0ng!Pass"}).get_json()
    listed = client.get("/api/qrcodes?limit=10&offset=0", headers=h).get_json()
    for row in listed["items"]:
        out.QRCodeOut.model_validate(row)
        assert "password_hash" not in row, "a password hash reached the client"
    # the protected QR also verifies the password flag is exposed
    one = client.get(f"/api/qrcodes/{qr['qr_id']}", headers=h).get_json()
    out.QRCodeOut.model_validate(one)
    assert one.get("has_password") == 1


def test_paginated_envelope_matches_the_model(client):
    client.post("/api/register", json=CREDS)
    mark_verified(CREDS["email"])
    tok = client.post("/api/login", json={"email": CREDS["email"],
                                          "password": CREDS["password"]}
                      ).get_json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    body = client.get("/api/qrcodes?limit=5&offset=0", headers=h).get_json()
    out.QRCodeListEnvelope.model_validate(body)
    assert {"items", "total", "limit", "offset"} <= set(body)


def test_analytics_responses_match_their_models(client):
    client.post("/api/register", json=CREDS)
    mark_verified(CREDS["email"])
    tok = client.post("/api/login", json={"email": CREDS["email"],
                                          "password": CREDS["password"]}
                      ).get_json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    qr = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "is_dynamic": True, "name": "A"}).get_json()
    client.get(f"/r/{qr['short_code']}")
    out.AnalyticsOverviewOut.model_validate(
        client.get("/api/analytics/overview", headers=h).get_json())
    detail = client.get(f"/api/qrcodes/{qr['qr_id']}/analytics",
                        headers=h).get_json()
    out.QRAnalyticsOut.model_validate(detail)
    for s in detail["scans"]:
        out.ScanOut.model_validate(s)


def test_scan_list_is_paginated_not_truncated(client):
    """
    Phase 5 audit: the per-QR scan list was capped at a hardcoded 100 with
    no total, so scans past 100 were unreachable and the truncation was
    invisible. Now it takes limit/offset and reports the real count.
    """
    client.post("/api/register", json=CREDS)
    mark_verified(CREDS["email"])
    tok = client.post("/api/login", json={"email": CREDS["email"],
                                          "password": CREDS["password"]}
                      ).get_json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    qr = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "is_dynamic": True, "name": "P"}).get_json()
    for _ in range(5):
        client.get(f"/r/{qr['short_code']}")

    windowed = client.get(
        f"/api/qrcodes/{qr['qr_id']}/analytics?limit=2&offset=0", headers=h).get_json()
    assert len(windowed["scans"]) == 2
    assert windowed["limit"] == 2 and windowed["offset"] == 0
    assert windowed["total"] == 5, "total must report the real count"

    second = client.get(
        f"/api/qrcodes/{qr['qr_id']}/analytics?limit=2&offset=2", headers=h).get_json()
    first_ids = {s["id"] for s in windowed["scans"]}
    second_ids = {s["id"] for s in second["scans"]}
    assert not (first_ids & second_ids), "the two pages overlap"


def test_bad_pagination_is_rejected(client):
    client.post("/api/register", json=CREDS)
    mark_verified(CREDS["email"])
    tok = client.post("/api/login", json={"email": CREDS["email"],
                                          "password": CREDS["password"]}
                      ).get_json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    qr = client.post("/api/generate", headers=h, json={
        "type": "url", "data": {"url": "https://example.com"},
        "is_dynamic": True, "name": "B"}).get_json()
    r = client.get(f"/api/qrcodes/{qr['qr_id']}/analytics?limit=99999",
                   headers=h)
    assert r.status_code == 400, "an out-of-range limit was accepted"


def test_health_and_message_shapes_match(client):
    out.HealthOut.model_validate(client.get("/api/health").get_json())
    r = client.post("/api/logout", headers={"Authorization": "Bearer x"})
    out.MessageOut.model_validate(r.get_json())


def test_legacy_bare_list_is_documented_as_such():
    """An inconsistency a client must handle should be named, not hidden."""
    assert contract.LEGACY_BARE_LIST
    for path in contract.LEGACY_BARE_LIST:
        assert path in contract.CONTRACT

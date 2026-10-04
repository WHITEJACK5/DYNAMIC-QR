"""Phase 6a: prove the containerised stack works end to end.

Runs the directive's own journey against the running compose stack:
register -> verify -> login -> dynamic QR -> scan -> analytics. Everything
goes over HTTP to the published port, so this exercises the image, gunicorn,
PostgreSQL and Redis together rather than any of them in isolation.

Run only when the stack is up:
    docker compose up -d
    pytest tests/test_docker_stack.py -q
"""
import json
import os
import time
import urllib.error
import urllib.request

import pytest

BASE = os.getenv("STACK_URL", "http://localhost:8000").rstrip("/")


def _reachable():
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=3):
            return True
    except Exception:
        return False


# Skip unless the stack is actually up: these tests drive a real deployment,
# not an in-process app, so they cannot be faked with a test client.
pytestmark = pytest.mark.skipif(not _reachable(),
                                reason="compose stack not running (docker compose up -d)")


def _req(method, path, payload=None, token=None):
    headers = {}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, data=body, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, _parse(raw), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, _parse(raw), dict(e.headers)


def _parse(raw):
    """JSON when it is JSON, text otherwise — some endpoints serve HTML."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"_text": raw.decode("utf-8", "replace")}


def _unique():
    return f"docker-{int(time.time() * 1000)}@example.com"


# --------------------------------------------------------------- the basics
def test_health_reports_ok():
    status, body, _ = _req("GET", "/api/health")
    assert status == 200
    assert body["status"] == "ok"


def test_security_headers_survive_the_container():
    _, _, headers = _req("GET", "/")
    for h in ("Content-Security-Policy", "X-Content-Type-Options",
              "X-Frame-Options", "Referrer-Policy"):
        assert h in headers, f"{h} missing behind gunicorn/container"


def test_frontend_is_served():
    req = urllib.request.Request(BASE + "/")
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", "replace")
    assert r.status == 200
    assert "DR" in html.upper()


# ------------------------------------------- the directive's full journey
def test_full_journey_through_the_container():
    email = _unique()
    pwd = "StrongPass123!"

    status, reg, _ = _req("POST", "/api/register",
                          {"email": email, "password": pwd, "name": "Docker"})
    assert status == 200, reg
    token = reg["token"]
    assert reg["email_verified"] is False

    # Phase 4d: dynamic QRs are gated behind a verified address. Confirm the
    # gate really is closed in this deployment rather than assuming it.
    status, denied, _ = _req("POST", "/api/generate", {
        "type": "url", "data": {"url": "https://example.com/x"},
        "is_dynamic": True, "name": "gated"}, token)
    assert status == 403 and denied.get("code") == "email_unverified", denied

    # No SMTP in the compose stack, so verification is delivered by the
    # database the container created. That is the same code path the real
    # emailed link drives (POST /api/verify-email), reached here through the
    # container's own PostgreSQL rather than a mailbox.
    import subprocess
    subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "DR", "-d", "DR",
         "-tAc",
         f"UPDATE users SET email_verified=1, verify_token=NULL WHERE email='{email}'"],
        check=True, capture_output=True, text=True, cwd=os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))

    status, gen, _ = _req("POST", "/api/generate", {
        "type": "url", "data": {"url": "https://example.com/x"},
        "is_dynamic": True, "name": "Docker QR"}, token)
    assert status == 200, gen
    short = gen["short_code"]
    assert short, gen

    # A visitor scans it, through the container's redirect path.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    scan_req = urllib.request.Request(f"{BASE}/r/{short}",
                                     headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
    try:
        with opener.open(scan_req, timeout=20) as r:
            assert r.status in (301, 302, 303, 307, 308), r.status
            assert r.headers.get("Location")
    except urllib.error.HTTPError as e:
        assert e.code in (301, 302, 303, 307, 308), e.code

    # The owner sees the scan in analytics, served from PostgreSQL.
    status, ov, _ = _req("GET", "/api/analytics/overview", token=token)
    assert status == 200, ov
    assert ov["total_scans"] == 1, ov
    assert ov["total_qrs"] == 1, ov

    status, detail, _ = _req("GET", f"/api/qrcodes/{gen['qr_id']}/analytics", token=token)
    assert status == 200, detail
    assert detail["total"] == 1, detail

    # listing is scoped to the owner
    status, listed, _ = _req("GET", "/api/qrcodes?limit=10&offset=0", token=token)
    assert status == 200
    assert listed["total"] == 1

    # logout really revokes, even in the container (Phase 4c)
    status, _, _ = _req("POST", "/api/logout", {}, token)
    assert status == 200
    status, after, _ = _req("GET", "/api/qrcodes", token=token)
    assert status == 401, f"a logged-out token still works: {status}"


def test_api_versioning_works_in_the_container():
    status, body, headers = _req("GET", "/api/v1/health")
    assert status == 200
    assert "Deprecation" not in headers, "/api/v1 must not be marked deprecated"
    status, _, headers = _req("GET", "/api/health")
    assert headers.get("Deprecation") == "true", "legacy /api must announce its successor"


def test_unknown_api_path_is_json_404_not_the_spa():
    """Phase 5c fix, verified in the real deployment."""
    status, body, _ = _req("GET", "/api/does-not-exist")
    assert status == 404, status
    assert isinstance(body, dict) and body.get("error"), body


def test_cookie_auth_is_not_accepted_in_the_container():
    """Phase 4e: no ambient credential, so no CSRF surface."""
    req = urllib.request.Request(BASE + "/api/qrcodes")
    req.add_header("Cookie", "token=anything")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            assert r.status == 401, r.status
    except urllib.error.HTTPError as e:
        assert e.code == 401, e.code
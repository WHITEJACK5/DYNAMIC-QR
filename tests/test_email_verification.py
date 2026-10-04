"""Phase 4d: email verification before an account can create dynamic QRs.

Directive: "Add email verification on registration before an account can
create dynamic QR codes."

Deliberately does NOT use the conftest mark_verified() shortcut — the whole
point of this file is to exercise the unverified path.
"""
import datetime
import hashlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as DR  # noqa: E402
from server import app  # noqa: E402
from app.extensions import get_session  # noqa: E402
from app.models import User  # noqa: E402
from app.repositories import users_repo  # noqa: E402
from app.services import mailer  # noqa: E402

MAIL_ENV = ("SMTP_HOST", "SMTP_PORT", "SMTP_FROM", "SMTP_USERNAME",
            "SMTP_PASSWORD", "SMTP_STARTTLS", "ALLOW_DEV_MAIL")

CREDS = {"email": "verify@example.com", "password": "StrongPass123!", "name": "V"}


@pytest.fixture(autouse=True)
def _no_smtp():
    saved = {k: os.environ.pop(k, None) for k in MAIL_ENV}
    yield
    for k, v in saved.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old_path = DR.DB_PATH
    DR.DB_PATH = tmp.name
    DR.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    DR.DB_PATH = old_path
    DR._rate_store.clear()


@pytest.fixture
def registered(client):
    r = client.post("/api/register", json=CREDS)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _token_for(email):
    r = app.test_client().post("/api/login", json={
        "email": email, "password": CREDS["password"]})
    return r.get_json()["token"]


def _dynamic(client, token, name="Dyn"):
    return client.post("/api/generate", json={
        "type": "url", "data": {"url": "https://example.com/x"},
        "is_dynamic": True, "name": name},
        headers={"Authorization": f"Bearer {token}"})


def _verify_now(email):
    s = get_session()
    try:
        users_repo.mark_email_verified(s, email)
    finally:
        s.close()


def _set_verify_token(email, raw, expires_in_hours=24):
    s = get_session()
    try:
        users_repo.set_verify_token(
            s, email, hashlib.sha256(raw.encode()).hexdigest(),
            (datetime.datetime.utcnow()
             + datetime.timedelta(hours=expires_in_hours)).isoformat())
    finally:
        s.close()


# ------------------------------------------------------------- the gate itself
def test_new_account_starts_unverified(registered):
    assert registered["email_verified"] is False


def test_unverified_account_cannot_create_a_dynamic_qr(client, registered):
    r = _dynamic(client, registered["token"])
    assert r.status_code == 403, r.get_json()
    body = r.get_json()
    assert body["code"] == "email_unverified"
    assert "verify" in body["error"].lower()


def test_unverified_account_can_still_create_a_static_qr(client, registered):
    """The gate is scoped to dynamic QRs, as the directive specifies."""
    r = client.post("/api/generate", json={
        "type": "url", "data": {"url": "https://example.com/static"}, "name": "S"},
        headers={"Authorization": f"Bearer {registered['token']}"})
    assert r.status_code == 200, r.get_json()


def test_verified_account_can_create_a_dynamic_qr(client, registered):
    _verify_now(CREDS["email"])
    r = _dynamic(client, registered["token"])
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["short_code"]


def test_verification_state_is_visible_on_the_user(client, registered):
    _token = registered["token"]
    me = client.get("/api/me", headers={"Authorization": f"Bearer {_token}"})
    assert me.status_code == 200
    assert me.get_json().get("email_verified") is False
    _verify_now(CREDS["email"])
    me2 = client.get("/api/me", headers={"Authorization": f"Bearer {_token}"})
    assert me2.get_json().get("email_verified") is True


# ------------------------------------------------------------- the verify link
def test_valid_token_verifies_the_account(client, registered):
    _set_verify_token(CREDS["email"], "raw-token-abc")
    r = client.post("/api/verify-email", json={"token": "raw-token-abc"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "verified"
    assert _dynamic(client, registered["token"]).status_code == 200


def test_verification_link_works_as_a_get_navigation(client, registered):
    """
    The link in the email is a plain URL a browser follows, so it is a GET.

    This test previously asserted only the status code, and passed against
    index.html: the catch-all page route answers unmatched /api/* paths with
    the SPA and status 200, so the route was POST-only in practice and the
    emailed link did nothing. Asserting the body is what catches that class
    of false pass.
    """
    _set_verify_token(CREDS["email"], "raw-token-get")
    r = client.get("/api/verify-email?token=raw-token-get")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    body = r.get_json()
    assert body["status"] == "verified", \
        f"GET did not verify; got {body} (HTML means the catch-all shadowed it)"
    # and the account is genuinely verified now
    assert _dynamic(client, registered["token"]).status_code == 200


def test_unknown_api_paths_return_json_404_not_the_spa(client):
    """A mistyped API URL must be a 404, not index.html with status 200."""
    r = client.get("/api/definitely-not-a-route")
    assert r.status_code == 404, f"got {r.status_code} for an unknown API path"
    assert r.is_json, "an unknown /api/ path returned the SPA instead of JSON"
    assert r.get_json()["error"] == "Not found"
    # the browser-facing catch-all still serves the SPA
    page = client.get("/some/spa/route")
    assert page.status_code == 200
    assert not page.is_json, "the SPA catch-all stopped working for non-API paths"


def test_token_is_single_use(client, registered):
    _set_verify_token(CREDS["email"], "one-shot")
    assert client.post("/api/verify-email", json={"token": "one-shot"}).status_code == 200
    replay = client.post("/api/verify-email", json={"token": "one-shot"})
    assert replay.status_code == 400
    assert "already-used" in replay.get_json()["error"]


def test_wrong_token_is_rejected(client, registered):
    _set_verify_token(CREDS["email"], "the-real-one")
    r = client.post("/api/verify-email", json={"token": "not-the-one"})
    assert r.status_code == 400


def test_expired_token_is_rejected(client, registered):
    _set_verify_token(CREDS["email"], "stale", expires_in_hours=-1)
    r = client.post("/api/verify-email", json={"token": "stale"})
    assert r.status_code == 400
    assert "expired" in r.get_json()["error"].lower()


def test_missing_token_is_a_400(client):
    assert client.post("/api/verify-email", json={}).status_code == 400


def test_raw_token_is_not_stored(client, registered):
    """Only the hash is persisted, so a database read cannot forge a link."""
    _set_verify_token(CREDS["email"], "secret-raw-value")
    s = get_session()
    try:
        u = s.query(User).filter(User.email == CREDS["email"]).one()
        assert u.verify_token != "secret-raw-value"
        assert u.verify_token == hashlib.sha256(b"secret-raw-value").hexdigest()
    finally:
        s.close()


# ----------------------------------------------------------------- the mailer
def test_registration_reports_honestly_when_mail_cannot_be_sent(registered):
    """No SMTP configured: the API must not claim the email was sent."""
    assert registered["verification_email_sent"] is False


def test_unconfigured_mailer_does_not_send(monkeypatch):
    calls = []
    monkeypatch.setattr("smtplib.SMTP", lambda *a, **k: calls.append(a))
    assert mailer.send("x@y.com", "s", "b") is False
    assert calls == [], "SMTP was contacted with no host configured"


def test_dev_mail_requires_an_explicit_opt_in():
    assert mailer.dev_mail_allowed() is False
    os.environ["ALLOW_DEV_MAIL"] = "1"
    assert mailer.dev_mail_allowed() is True


def test_resend_never_reveals_whether_an_account_exists(client):
    """Non-enumeration: every outcome is the same 202 and the same body.

    Differing on 'unknown account' vs 'delivery failed' would let an
    attacker confirm which addresses are registered, which is exactly what
    credential stuffing and targeted phishing need.
    """
    known = client.post("/api/resend-verification", json={"email": CREDS["email"]})
    unknown = client.post("/api/resend-verification", json={"email": "nobody@nowhere.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.get_json() == unknown.get_json()


def test_resend_of_a_verified_account_looks_identical_to_an_unknown_one(client, registered):
    _verify_now(CREDS["email"])
    verified = client.post("/api/resend-verification", json={"email": CREDS["email"]})
    unknown = client.post("/api/resend-verification", json={"email": "nobody@nowhere.com"})
    assert verified.status_code == unknown.status_code == 202
    assert verified.get_json() == unknown.get_json()


def test_resend_does_not_claim_delivery_when_smtp_is_absent(client, registered):
    """It stays silent about the failure (to avoid enumeration) and logs it."""
    r = client.post("/api/resend-verification", json={"email": CREDS["email"]})
    assert r.status_code == 202
    assert "sent" in r.get_json()["status"]
    # the account is still unverified, so the gate still applies
    assert _dynamic(client, registered["token"]).status_code == 403


def test_resend_does_send_when_smtp_is_available(client, registered, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "smtp_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subj, body: sent.append(to) or True)
    r = client.post("/api/resend-verification", json={"email": CREDS["email"]})
    assert r.status_code == 202
    assert sent == [CREDS["email"]]


def test_resend_rate_limited(client, registered):
    """Abuse control is rate limiting, not a distinguishing status code."""
    codes = {client.post("/api/resend-verification",
                         json={"email": CREDS["email"]}).status_code
             for _ in range(8)}
    assert 429 in codes, f"resend is not rate limited: {codes}"


def test_verify_url_contains_the_token():
    url = mailer.build_verify_url("https://app.example.com/", "tok123")
    assert url == "https://app.example.com/api/verify-email?token=tok123"

"""Phase 10: the review-capture journey, end to end.

The directive: "scanning a dynamic QR of type `review` should route the
customer to a lightweight review form (rating + free text), not just redirect
to a static link."

These tests prove the full journey: scan → form → submit → stored → redirect.
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
from conftest import mark_verified  # noqa: E402


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


def _review_qr(client, redirect_url="https://example.com/thanks"):
    """Create a review QR and return its short_code."""
    client.post("/api/register", json={
        "email": "review@example.com", "password": "StrongPass123!", "name": "R"})
    mark_verified("review@example.com")
    r = client.post("/api/login", json={
        "email": "review@example.com", "password": "StrongPass123!"})
    token = r.get_json()["token"]
    g = client.post("/api/generate", json={
        "type": "review",
        "data": {"redirectUrl": redirect_url},
        "is_dynamic": True, "name": "Review QR"},
        headers={"Authorization": f"Bearer {token}"})
    return g.get_json()["short_code"]


# ------------------------------------------------------------- the journey
def test_scanning_a_review_qr_serves_a_form_not_a_redirect(client):
    code = _review_qr(client)
    r = client.get(f"/r/{code}")
    assert r.status_code == 200, "a review QR must serve the form, not a 302"
    body = r.get_data(as_text=True)
    assert "star" in body.lower() or "rating" in body.lower()
    assert "review" in body.lower()


def test_a_non_review_qr_still_redirects(client):
    """The capture flow must not change every other QR type."""
    client.post("/api/register", json={
        "email": "url@example.com", "password": "StrongPass123!", "name": "U"})
    mark_verified("url@example.com")
    token = client.post("/api/login", json={
        "email": "url@example.com", "password": "StrongPass123!"}).get_json()["token"]
    code = client.post("/api/generate", json={
        "type": "url", "data": {"url": "https://example.com"},
        "is_dynamic": True, "name": "URL"},
        headers={"Authorization": f"Bearer {token}"}).get_json()["short_code"]
    r = client.get(f"/r/{code}")
    assert r.status_code in (301, 302, 303, 307, 308), \
        f"a url QR must still redirect, got {r.status_code}"


def test_submitting_a_review_stores_it_and_returns_the_redirect(client):
    code = _review_qr(client, redirect_url="https://example.com/after")
    r = client.post("/api/reviews", json={
        "short_code": code, "rating": 5, "review_text": "Great service!"})
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body["status"] == "recorded"
    assert body["review_id"]
    assert body["redirect"] == "https://example.com/after"


def test_a_review_is_visible_to_its_owner(client):
    code = _review_qr(client)
    client.post("/api/reviews", json={
        "short_code": code, "rating": 4, "review_text": "Good"})
    token = client.post("/api/login", json={
        "email": "review@example.com", "password": "StrongPass123!"}).get_json()["token"]
    r = client.get("/api/reviews", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    items = r.get_json()["items"]
    assert len(items) == 1
    assert items[0]["rating"] == 4
    assert items[0]["review_text"] == "Good"


def test_rating_must_be_between_1_and_5(client):
    code = _review_qr(client)
    for bad in (0, 6, -1, "abc"):
        r = client.post("/api/reviews", json={
            "short_code": code, "rating": bad, "review_text": "x"})
        assert r.status_code == 400, f"rating {bad} was accepted"


def test_an_unknown_short_code_is_a_404(client):
    r = client.post("/api/reviews", json={
        "short_code": "nope1234", "rating": 5, "review_text": "x"})
    assert r.status_code == 404


def test_the_summary_endpoint_returns_aggregates(client):
    code = _review_qr(client)
    client.post("/api/reviews", json={
        "short_code": code, "rating": 5, "review_text": "Great"})
    client.post("/api/reviews", json={
        "short_code": code, "rating": 1, "review_text": "Terrible"})
    token = client.post("/api/login", json={
        "email": "review@example.com", "password": "StrongPass123!"}).get_json()["token"]
    r = client.get("/api/reviews/summary", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["total"] == 2
    assert body["average_rating"] == 3.0
    assert body["distribution"]["5"] == 1
    assert body["distribution"]["1"] == 1


def test_flagged_reviews_are_surfaced(client):
    code = _review_qr(client)
    client.post("/api/reviews", json={
        "short_code": code, "rating": 1, "review_text": "Awful"})
    token = client.post("/api/login", json={
        "email": "review@example.com", "password": "StrongPass123!"}).get_json()["token"]
    r = client.get("/api/reviews/flagged", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.get_json()) == 1
    assert r.get_json()[0]["rating"] == 1


def test_export_returns_csv(client):
    code = _review_qr(client)
    client.post("/api/reviews", json={
        "short_code": code, "rating": 5, "review_text": "Great"})
    token = client.post("/api/login", json={
        "email": "review@example.com", "password": "StrongPass123!"}).get_json()["token"]
    r = client.get("/api/reviews/export", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "rating" in r.get_data(as_text=True).splitlines()[0]


def test_reviews_are_scoped_to_the_owner(client):
    """User A must not see user B's reviews."""
    code_a = _review_qr(client)
    client.post("/api/reviews", json={
        "short_code": code_a, "rating": 5, "review_text": "A's review"})
    # a second user
    client.post("/api/register", json={
        "email": "other@example.com", "password": "StrongPass123!", "name": "O"})
    mark_verified("other@example.com")
    token_b = client.post("/api/login", json={
        "email": "other@example.com", "password": "StrongPass123!"}).get_json()["token"]
    r = client.get("/api/reviews", headers={"Authorization": f"Bearer {token_b}"})
    assert r.get_json()["total"] == 0

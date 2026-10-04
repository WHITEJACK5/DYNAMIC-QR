"""Phase 5a: authorization boundaries between accounts.

Directive: "Add authorization boundary tests: verify user A cannot
read/update/delete user B's QR codes by guessing/incrementing IDs. This
is currently untested and is a real vulnerability class if it's broken."

The pattern under test is horizontal privilege escalation via object id
enumeration. Every test creates a resource as user A and then attacks it
as user B with a valid session, so a missing ownership filter shows up as a
200 instead of a 404.

An important detail: not-found and not-yours must BOTH be 404. Returning
403 would confirm the id exists, which leaks the shape of other users' data.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key-for-ci-must-be-long-enough-32chars"
os.environ["BASE_URL"] = "http://localhost:5000"

import server as DR  # noqa: E402
from server import app  # noqa: E402
from conftest import mark_verified  # noqa: E402

A = {"email": "alice@example.com", "password": "StrongPass123!", "name": "Alice"}
B = {"email": "bob@example.com", "password": "StrongPass123!", "name": "Bob"}


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


def _account(client, creds):
    r = client.post("/api/register", json=creds)
    assert r.status_code == 200, r.get_json()
    mark_verified(creds["email"])  # Phase 4d: dynamic QRs need verification
    r = client.post("/api/login", json={"email": creds["email"],
                                        "password": creds["password"]})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["token"]


@pytest.fixture
def two_users(client):
    return _account(client, A), _account(client, B)


def _alice_qr(client, token, name="Alice QR", **extra):
    body = {"type": "url", "data": {"url": "https://example.com/alice"},
            "is_dynamic": True, "name": name}
    body.update(extra)
    r = client.post("/api/generate", json=body, headers=_h(token))
    assert r.status_code == 200, f"setup failed: {r.status_code} {r.get_json()}"
    body = r.get_json()
    # /api/generate returns qr_id, not id
    return {"id": body["qr_id"], "name": name, "short_code": body.get("short_code")}


@pytest.fixture
def alice_qr(client, two_users):
    token_a, _token_b = two_users
    return _alice_qr(client, token_a)


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _items(body):
    """The listed rows, whether the endpoint returned a bare list (the
    documented legacy shape with no pagination params) or the envelope."""
    if isinstance(body, list):
        return body
    return body.get("items", [])


def _total(body):
    if isinstance(body, list):
        return len(body)
    return body.get("total", len(body.get("items", [])))


# ------------------------------------------------------------------- read
def test_bob_cannot_read_alices_qr_by_id(client, two_users, alice_qr):
    _token_a, token_b = two_users
    r = client.get(f"/api/qrcodes/{alice_qr['id']}", headers=_h(token_b))
    assert r.status_code == 404, f"bob read alice's QR: {r.status_code} {r.get_json()}"


def test_bob_cannot_download_alices_qr(client, two_users, alice_qr):
    _token_a, token_b = two_users
    r = client.get(f"/api/download/{alice_qr['id']}?format=png", headers=_h(token_b))
    assert r.status_code == 404, f"bob downloaded alice's QR: {r.status_code}"


def test_bob_cannot_duplicate_alices_qr(client, two_users, alice_qr):
    _token_a, token_b = two_users
    r = client.post(f"/api/qrcodes/{alice_qr['id']}/duplicate", headers=_h(token_b))
    assert r.status_code == 404, f"bob duplicated alice's QR: {r.status_code}"


# ------------------------------------------------------------------ update
def test_bob_cannot_rename_alices_qr(client, two_users, alice_qr):
    _token_a, token_b = two_users
    r = client.put(f"/api/qrcodes/{alice_qr['id']}", json={"name": "Stolen"},
                   headers=_h(token_b))
    assert r.status_code == 404, f"bob renamed alice's QR: {r.status_code}"


def test_bobs_update_did_not_actually_change_it(client, two_users, alice_qr):
    """Not just a refusal: the data must be untouched."""
    token_a, token_b = two_users
    client.put(f"/api/qrcodes/{alice_qr['id']}", json={"name": "Stolen"},
               headers=_h(token_b))
    mine = client.get(f"/api/qrcodes/{alice_qr['id']}", headers=_h(token_a))
    assert mine.status_code == 200
    assert mine.get_json()["name"] == alice_qr["name"]


# ------------------------------------------------------------------ delete
def test_bob_cannot_delete_alices_qr(client, two_users, alice_qr):
    _token_a, token_b = two_users
    r = client.delete(f"/api/qrcodes/{alice_qr['id']}", headers=_h(token_b))
    assert r.status_code == 404, f"bob deleted alice's QR: {r.status_code}"


def test_alices_qr_survives_bobs_delete(client, two_users, alice_qr):
    token_a, token_b = two_users
    client.delete(f"/api/qrcodes/{alice_qr['id']}", headers=_h(token_b))
    still = client.get(f"/api/qrcodes/{alice_qr['id']}", headers=_h(token_a))
    assert still.status_code == 200, "alice's QR was destroyed by bob's delete"


# -------------------------------------------------------------- enumeration
def test_incrementing_ids_never_reveals_another_users_data(client, two_users, alice_qr):
    """Walk the whole id space around alice's QR as Bob."""
    _token_a, token_b = two_users
    target = alice_qr["id"]
    for candidate in range(max(1, target - 5), target + 6):
        r = client.get(f"/api/qrcodes/{candidate}", headers=_h(token_b))
        assert r.status_code in (404,), \
            f"id {candidate} returned {r.status_code} to another user"
        assert r.get_json().get("error") == "Not found"


def test_listing_only_ever_returns_your_own(client, two_users, alice_qr):
    token_a, token_b = two_users
    for query in ("", "?limit=50&offset=0"):
        r = client.get(f"/api/qrcodes{query}", headers=_h(token_b))
        assert r.status_code == 200
        ids = [q["id"] for q in _items(r.get_json())]
        assert alice_qr["id"] not in ids, f"alice's QR leaked in listing {query!r}"


def test_owner_count_is_per_account(client, two_users, alice_qr):
    token_a, token_b = two_users
    a = client.get("/api/qrcodes?limit=50&offset=0", headers=_h(token_a)).get_json()
    b = client.get("/api/qrcodes?limit=50&offset=0", headers=_h(token_b)).get_json()
    assert _total(a) == 1, f"alice owns 1 QR, saw {_total(a)}"
    assert _total(b) == 0, f"bob owns nothing, saw {_total(b)}"


# ---------------------------------------------------- the 404-not-403 rule
def test_other_peoples_ids_return_404_not_403(client, two_users, alice_qr):
    """
    403 would confirm the id exists, which is itself a leak: it tells an
    attacker which ids are real and lets them map a victim's inventory.
    """
    _token_a, token_b = two_users
    for method, path in (("GET", f"/api/qrcodes/{alice_qr['id']}"),
                         ("PUT", f"/api/qrcodes/{alice_qr['id']}"),
                         ("DELETE", f"/api/qrcodes/{alice_qr['id']}")):
        kwargs = {"headers": _h(token_b)}
        if method == "PUT":
            kwargs["json"] = {"name": "x"}
        r = getattr(client, method.lower())(path, **kwargs)
        assert r.status_code == 404, f"{method} {path} -> {r.status_code}"


def test_nonexistent_id_and_someone_elses_id_look_identical(client, two_users, alice_qr):
    """An attacker must not be able to tell the two apart."""
    _token_a, token_b = two_users
    real = client.get(f"/api/qrcodes/{alice_qr['id']}", headers=_h(token_b))
    fake = client.get("/api/qrcodes/99999999", headers=_h(token_b))
    assert real.status_code == fake.status_code
    assert real.get_json() == fake.get_json()


# ------------------------------------------------------------------ folders
def test_folders_are_scoped_to_the_owner(client, two_users):
    """
    Registration auto-creates each account's own "My QR Codes" folder, so
    Bob legitimately has one folder. The boundary is that it is HIS, and
    that Alice's extra folder never appears in his listing.
    """
    token_a, token_b = two_users
    created = client.post("/api/folders", json={"name": "Alice private"},
                          headers=_h(token_a))
    assert created.status_code in (200, 201), created.get_json()
    alice_folder_id = created.get_json()["id"]

    mine = _items(client.get("/api/folders", headers=_h(token_b)).get_json())
    assert all(f["name"] != "Alice private" for f in mine), \
        "alice's folder appeared in bob's listing"
    assert alice_folder_id not in [f["id"] for f in mine]

    hers = _items(client.get("/api/folders", headers=_h(token_a)).get_json())
    assert alice_folder_id in [f["id"] for f in hers]
    # every folder is attributed to the caller
    for f in mine:
        assert f["user_id"] == 2, f"folder {f['id']} belongs to {f['user_id']}"


def test_created_folder_is_always_attributed_to_the_caller(client, two_users):
    """A client cannot create a folder inside someone else's account by
    sending a user_id.

    create_for_user only returns {id, name}, so ownership is verified
    through the listing — which is the stronger check anyway, because it
    proves where the row actually landed rather than what the handler
    echoed back.
    """
    token_a, token_b = two_users
    r = client.post("/api/folders", json={"name": "Sneaky", "user_id": 1},
                    headers=_h(token_b))
    assert r.status_code in (200, 201), r.get_json()
    new_id = r.get_json()["id"]

    mine = _items(client.get("/api/folders", headers=_h(token_b)).get_json())
    landed = [f for f in mine if f["id"] == new_id]
    assert landed, "the folder was created somewhere bob cannot see it"
    assert landed[0]["user_id"] == 2, \
        f"a client-supplied user_id was trusted: {landed[0]}"

    # and it must NOT be visible to alice, whose id the client tried to use
    hers = _items(client.get("/api/folders", headers=_h(token_a)).get_json())
    assert new_id not in [f["id"] for f in hers]


def test_templates_are_scoped_to_the_owner(client, two_users):
    token_a, token_b = two_users
    created = client.post("/api/templates", json={"name": "Alice template"},
                          headers=_h(token_a))
    assert created.status_code in (200, 201), created.get_json()
    mine = _items(client.get("/api/templates", headers=_h(token_b)).get_json())
    assert all(t["name"] != "Alice template" for t in mine)


# ---------------------------------------------------------------- analytics
def test_analytics_are_scoped_to_the_account(client, two_users, alice_qr):
    _token_a, token_b = two_users
    r = client.get("/api/analytics/overview", headers=_h(token_b))
    assert r.status_code == 200
    body = r.get_json()
    total = body.get("total_scans", body.get("total", 0))
    assert total == 0, f"bob sees alice's scan totals: {body}"


# ---------------------------------------------------------------- anonymous
def test_anonymous_cannot_read_someone_elses_qr(client, alice_qr):
    r = client.get(f"/api/qrcodes/{alice_qr['id']}")
    assert r.status_code == 401


def test_a_forged_token_is_rejected(client, alice_qr):
    import jwt as _jwt
    from app.config import JWT_ALGO

    forged = _jwt.encode({"user_id": 1, "email": A["email"], "typ": "access",
                          "jti": "forged", "exp": 9_999_999_999},
                         "not-the-real-secret", algorithm=JWT_ALGO)
    r = client.get(f"/api/qrcodes/{alice_qr['id']}",
                   headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401

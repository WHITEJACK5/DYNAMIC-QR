"""Phase 2b: one endpoint must not have two input contracts.

Found by auditing the directive's clause "every endpoint gets an explicit
input schema". The multipart branch of /api/generate read request.form
directly with no validation, so it accepted input the JSON path rejects —
and the multipart branch is what a browser actually sends.

Before this, on the same endpoint:

    POST /api/generate  fg_color=not-a-colour  (json)      -> 400
    POST /api/generate  fg_color=not-a-colour  (multipart) -> 200
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
from app.schemas import GenerateFormRequest  # noqa: E402


@pytest.fixture
def client():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp.close()
    old = DR.DB_PATH
    DR.DB_PATH = tmp.name
    DR.init_db()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    DR.DB_PATH = old
    DR._rate_store.clear()


def _form(client, **fields):
    return client.post("/api/generate", data=fields,
                       content_type="multipart/form-data")


def _json(client, **fields):
    return client.post("/api/generate", json=fields)


# ------------------------------------------------------------- parity of rules
@pytest.mark.parametrize("field,value", [
    ("fg_color", "not-a-colour"),
    ("bg_color", "#GGGGGG"),
    ("frame_color", "purple"),
])
def test_multipart_rejects_bad_colours_like_json_does(client, field, value):
    r = _form(client, type="url", data='{"url":"https://example.com"}',
              **{field: value})
    assert r.status_code == 400, (
        f"multipart accepted {field}={value!r} with {r.status_code}")
    assert "color" in r.get_json()["error"].lower()


@pytest.mark.parametrize("field,value", [
    ("scan_limit", "abc"),
    ("scan_limit", "0"),
    ("scan_limit", "-5"),
    ("scan_limit", "99999999999999999999"),
])
def test_multipart_rejects_bad_scan_limits_like_json_does(client, field, value):
    """
    Both paths now reject a scan_limit that cannot mean what was intended.

    They used to coerce it to "no limit", so a merchant who mistyped 100
    silently got an unlimited QR — invisible, and the opposite of what a
    limit is for. Pydantic turns the bad value into a clean 400, so the
    old "never a 500" justification for leniency did not hold.
    """
    r = _form(client, type="url", data='{"url":"https://example.com"}',
              **{field: value})
    assert r.status_code == 400, (
        f"multipart accepted scan_limit={value!r} with {r.status_code}")
    assert "scan_limit" in r.get_json()["error"]


def test_scan_limit_coercion_is_identical_on_both_paths():
    """One rule, one outcome, whichever way the request arrives."""
    from app.schemas import GenerateRequest

    for value in ("abc", "0", "-5", "", None, "25", 25):
        json_val = _coerce(GenerateRequest, value)
        form_val = _coerce(GenerateFormRequest, value)
        assert json_val == form_val, (
            f"scan_limit={value!r}: json={json_val!r} form={form_val!r}")


def _coerce(model, value):
    from pydantic import ValidationError

    try:
        return model.model_validate({"scan_limit": value}).scan_limit
    except ValidationError:
        return "rejected"


def test_a_valid_multipart_request_still_works(client):
    r = _form(client, type="url", data='{"url":"https://example.com"}',
              fg_color="#112233", bg_color="#FFFFFF", name="Form QR")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["image_base64"].startswith("data:image/png;base64,")


def test_an_empty_multipart_request_still_gets_defaults(client):
    r = _form(client)
    assert r.status_code == 200, r.get_json()


def test_is_dynamic_is_read_from_the_form_string(client):
    """A browser sends the literal string "true", not a boolean."""
    assert GenerateFormRequest.model_validate(
        {"is_dynamic": "true"}).is_dynamic is True
    assert GenerateFormRequest.model_validate(
        {"is_dynamic": "false"}).is_dynamic is False
    assert GenerateFormRequest.model_validate({}).is_dynamic is False


def test_blank_values_fall_back_to_defaults():
    f = GenerateFormRequest.model_validate(
        {"fg_color": "", "type": "", "data": ""})
    assert f.fg_color == "#0A0A0A"
    assert f.type == "url"
    assert f.data == "{}"


def test_scan_limit_is_coerced_to_int():
    assert GenerateFormRequest.model_validate(
        {"scan_limit": "25"}).scan_limit == 25
    assert GenerateFormRequest.model_validate(
        {"scan_limit": ""}).scan_limit is None


def test_unknown_form_fields_are_ignored():
    """Matches the JSON schema's extra="ignore", so a stray field from a
    form post is not an error."""
    f = GenerateFormRequest.model_validate({"type": "url", "wat": "1"})
    assert f.type == "url"


# ------------------------------------------------------ structural guarantee
def test_the_multipart_branch_no_longer_reads_request_form_raw():
    """The regression itself: no unvalidated request.form access in the
    generate handler."""
    import inspect as _inspect

    from app.routes import qr as qr_routes

    src = _inspect.getsource(qr_routes.generate)
    before, _, _after = src.partition("# Access-control options")
    assert "GenerateFormRequest.model_validate" in before
    # raw form reads would reintroduce the two-contract problem.
    # Comments are excluded: this handler documents what it used to do, and
    # matching the prose would make the guard test a comment-matching test.
    code = [ln for ln in before.splitlines() if not ln.strip().startswith("#")]
    for line in code:
        if "request.form" in line:
            assert "form.items()" in line, (
                f"unvalidated form read: {line.strip()}")
    assert "request.form.get" not in "\n".join(code), (
        "generate() still reads request.form directly")


def test_json_and_multipart_agree_on_the_same_bad_input(client):
    """The property, stated once: identical verdicts on both paths."""
    cases = [("fg_color", "not-a-colour"),   # both must 400
             ("bg_color", "#GGGGGG"),        # both must 400
             ("scan_limit", "abc"),          # both must 400
             ("scan_limit", "0")]            # both must 400
    for field, value in cases:
        a = _json(client, type="url", data={"url": "https://example.com"},
                  **{field: value})
        b = _form(client, type="url", data='{"url":"https://example.com"}',
                  **{field: value})
        assert a.status_code == b.status_code, (
            f"{field}={value!r}: json={a.status_code} multipart={b.status_code}")

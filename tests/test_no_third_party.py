"""Phase 1d: no silent third-party exfiltration of preview content.

Regression test for the api.qrserver.com fallback: user-entered QR content
must never be sent to an undisclosed external service. Previews use our own
/api/preview only and fail with a clear error.
"""
import os

HERE = os.path.dirname(os.path.dirname(__file__))


def _read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


def test_no_qrserver_references():
    for rel in ("static/js/app.js", "frontend/index.html",
                "frontend/dashboard.html"):
        src = _read(rel)
        assert "qrserver" not in src.lower(), f"qrserver leak in {rel}"


def test_no_unused_qrcodejs_cdn():
    src = _read("frontend/index.html")
    assert "qrcodejs" not in src.lower(), "dead qrcodejs CDN still loaded"


def test_preview_fails_closed_with_disclosure():
    src = _read("static/js/app.js")
    # preview() must not build an external fallback URL
    assert "api.qrserver.com" not in src
    # failure path must tell the user nothing left the machine
    assert "No data was sent to any third party" in src

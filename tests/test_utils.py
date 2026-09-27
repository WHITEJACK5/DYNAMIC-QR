"""Phase 2a: pure-utils parity tests (no Flask/DB/network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

from app.utils import (
    build_gs1_content,
    build_qr_content,
    detect_device,
    generate_short_code,
    hex_to_rgb,
    validate_email_format,
    validate_password_strength,
)


def test_hex_to_rgb():
    assert hex_to_rgb("#0A0A0A") == (10, 10, 10)
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("#fff") == (255, 255, 255)


def test_short_code_entropy():
    codes = {generate_short_code() for _ in range(200)}
    assert len(codes) > 190  # collisions ~impossible at 62^8
    assert all(len(c) == 8 for c in codes)


def test_email_validation():
    assert validate_email_format("a@b.com") is True
    assert validate_email_format("bad") is False
    assert validate_email_format("you@nare.local") is True  # permissive fallback


def test_password_strength():
    ok, _ = validate_password_strength("StrongPass123!")
    assert ok is True
    ok, msg = validate_password_strength("short")
    assert ok is False and "8" in msg


def test_qr_content_types():
    assert build_qr_content("url", {"url": "example.com"}) == "https://example.com"
    assert build_qr_content("wifi", {"ssid": "S", "password": "P"}) == "WIFI:T:WPA;S:S;P:P;H:false;;"
    assert "VCARD" in build_qr_content("vcard", {"name": "A B"})
    assert build_gs1_content({"gtin": "09506000134352", "lot": "X"}).startswith("https://id.gs1.org/01/")


def test_detect_device():
    d, b, o = detect_device("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120")
    assert d == "Desktop" and b == "Chrome" and o == "Windows"
    d, _, o = detect_device("Mozilla/5.0 (Linux; Android 10)")
    assert o == "Android"


def test_parity_with_consumers():
    """app.utils is the single source: its consumers must resolve to it.

    After the Phase 2 route split there is no wrapper layer in server.py, so
    parity is asserted by checking that the modules which use these helpers
    (renderer, redirect service, schemas) import the very same functions.
    """
    from app import utils
    from app.schemas import validate_email_format as schema_email
    from app.services import redirect_service
    from app.services import render

    assert render.hex_to_rgb is utils.hex_to_rgb
    assert render.create_qr_image is not None
    assert redirect_service.detect_device is utils.detect_device
    assert schema_email is utils.validate_email_format
    # and the values agree with the originals
    assert hex_to_rgb("#00FF88") == (0, 255, 136)
    assert build_qr_content("url", {"url": "https://example.com"}) == "https://example.com"
    assert detect_device("x")[0] == "Desktop"

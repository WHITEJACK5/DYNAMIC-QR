"""Phase 2a: pure-utils parity tests (no Flask/DB/network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-must-be-long-enough-32chars")

from core.utils import (
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


def test_parity_with_app():
    """core.utils must match app.py wrappers exactly (same behavior post-extract)."""
    import app as nare

    assert nare.hex_to_rgb("#00FF88") == hex_to_rgb("#00FF88")
    assert nare.build_qr_content("url", {"url": "https://example.com"}) == build_qr_content(
        "url", {"url": "https://example.com"}
    )
    assert nare.detect_device("x") == detect_device("x")
    assert nare.validate_email_format("a@b.com") == validate_email_format("a@b.com")

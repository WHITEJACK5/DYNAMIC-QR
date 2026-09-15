"""Phase 2q: redirect decisions are pure (no Flask/DB/network)."""
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from werkzeug.security import generate_password_hash

from core.redirect_service import decide, resolve_target


def _row(**kw):
    base = {
        "content": "https://example.com",
        "type": "url",
        "is_dynamic": 0,
        "expiry_date": None,
        "scan_limit": None,
        "scan_count": 0,
        "has_password": 0,
        "password_hash": None,
        "data_json": None,
    }
    base.update(kw)
    return base


def test_missing():
    assert decide(None, None)["action"] == "missing"


def test_expiry():
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).isoformat()
    future = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat()
    assert decide(_row(expiry_date=past), None) == {"action": "gone", "message": "This QR has expired"}
    assert decide(_row(expiry_date=future), None)["action"] == "ok"
    assert decide(_row(expiry_date="not-a-date"), None)["action"] == "ok"  # ignored, legacy


def test_scan_limit():
    assert decide(_row(scan_limit=5, scan_count=5), None)["message"] == "Scan limit reached"
    assert decide(_row(scan_limit=5, scan_count=4), None)["action"] == "ok"


def test_password():
    h = generate_password_hash("Secret123!")
    r = _row(has_password=1, password_hash=h)
    assert decide(r, None)["action"] == "password"
    assert decide(r, "wrong")["action"] == "password"
    assert decide(r, "Secret123!")["action"] == "ok"


def test_smart_rules():
    import json as _j

    data = _j.dumps({
        "primaryUrl": "https://example.com/default",
        "rules": [
            {"condition": "os:android", "url": "https://play.google.com"},
            {"condition": "os:ios", "url": "https://apps.apple.com"},
        ],
    })
    r = _row(type="smarturl", is_dynamic=1, content="https://example.com/default", data_json=data)
    d = decide(r, None, "Mozilla/5.0 (Linux; Android 10)")
    assert (d["target"], d["smart"]) == ("https://play.google.com", True)
    d = decide(r, None, "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0)")
    assert d["target"] == "https://apps.apple.com"
    d = decide(r, None, "Mozilla/5.0 (Windows NT 10.0)")
    assert (d["target"], d["smart"]) == ("https://example.com/default", False)
    # static smart rows never resolve (legacy guard)
    r2 = _row(type="smarturl", is_dynamic=0, data_json=data)
    assert decide(r2, None, "Mozilla/5.0 (Linux; Android 10)")["smart"] is False


def test_resolve_string_rules_and_lang():
    r = _row(data_json='{"primaryUrl": "https://d.example", "rules": "lang:fr -> https://fr.example"}')
    assert resolve_target(r, "Mozilla/5.0", "fr-FR,fr;q=0.9") == "https://fr.example"
    assert resolve_target(r, "Mozilla/5.0", "en-US") == "https://d.example"
    assert resolve_target(_row(), "x") == "https://example.com"

"""Phase 4c client half: the frontend must survive 15-minute access tokens.

Shortening the access token from 7 days to 15 minutes would log every user
out every 15 minutes unless the client renews it. These tests guard the
renewal wiring, because a server-only change here is a change that breaks
the product.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


SESSION = "static/js/session.js"


def test_session_module_exists():
    assert os.path.isfile(os.path.join(HERE, SESSION))


def test_session_module_stores_the_refresh_token():
    src = _read(SESSION)
    assert "DR_refresh" in src
    assert "storeSession" in src


def test_renewal_happens_before_the_token_expires():
    """The refresh must be scheduled inside the 15-minute lifetime."""
    src = _read(SESSION)
    m = re.search(r"REFRESH_BEFORE_MS\s*=\s*(\d+)\s*\*\s*60\s*\*\s*1000", src)
    assert m, "REFRESH_BEFORE_MS not found in minutes"
    minutes = int(m.group(1))
    assert minutes < 15, f"refresh at {minutes} min is not before the 15 min expiry"
    assert minutes > 10, f"refreshing at {minutes} min is needlessly often"


def test_renewal_calls_the_refresh_endpoint_without_a_token_in_the_url():
    src = _read(SESSION)
    assert "/api/refresh" in src
    # Phase 4a still holds on the new code path
    assert "?token=" not in src
    assert "&token=" not in src


def test_rotation_is_persisted_so_the_old_refresh_token_is_not_reused():
    src = _read(SESSION)
    assert re.search(r"setItem\('DR_refresh',\s*j\.refresh_token", src), \
        "the rotated refresh token must be stored"


def test_a_401_from_refresh_clears_the_session():
    """A revoked/expired refresh token must not cause an endless 401 loop."""
    src = _read(SESSION)
    assert re.search(r"status\s*===\s*401", src)
    assert "clearSession()" in src


def test_renewal_is_retried_when_the_tab_becomes_visible():
    """A sleeping laptop returns with an expired access token."""
    src = _read(SESSION)
    assert "visibilitychange" in src
    assert "refreshAccessToken" in src


def test_logout_revokes_server_side():
    """Clearing localStorage alone would leave a valid token usable."""
    src = _read(SESSION)
    assert "/api/logout" in src
    assert re.search(r"async function logout", src)


def test_spa_uses_the_session_helper_instead_of_raw_setitem():
    src = _read("static/js/app.js")
    assert "DRSession.storeSession" in src, \
        "login must store the access/refresh pair via the session helper"
    # No raw write of the access token: a silent fallback would leave the
    # user with a 15-minute token and no way to renew it.
    assert "localStorage.setItem('DR_token', j.token)" not in src, \
        "login still writes the access token without the refresh token"


def test_session_module_is_loaded_on_every_page_that_authenticates():
    """
    Phase 8 moved the frontend to React, so session.js no longer exists as a
    separate file. The logic now lives in src/session.ts and is imported by
    the pages that authenticate. The test follows the code, not the filename.
    """
    src = _read(os.path.join("frontend", "src", "session.ts"))
    for needed in ("/api/refresh", "/api/logout", "DR_refresh", "visibilitychange"):
        assert needed in src, f"session.ts is missing {needed}"


def test_dashboard_handles_revoked_and_expired_tokens():
    src = _read("frontend/dashboard.html")
    for word in ("revoked", "expired"):
        assert word in src, f"dashboard does not handle '{word}' tokens"


@pytest.mark.parametrize("page", ["frontend/index.html", "frontend/dashboard.html"])
def test_no_page_puts_a_token_in_a_url(page):
    src = _read(page)
    for bad in ("?token=${", "&token=${", "?token='", "&token='"):
        assert bad not in src, f"{page} builds a token URL ({bad})"

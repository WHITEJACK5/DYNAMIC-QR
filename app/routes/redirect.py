"""The dynamic QR redirect: expiry, scan limit, password gate, smart-URL routing, scan tracking."""

import datetime
from html import escape

from flask import Blueprint, redirect as flask_redirect, request

from app.config import logger
from app.extensions import get_session
from app.repositories import qr_repo, scans_repo
from app.services import redirect_service
from app.services.geo import enrich_scan_geo
from app.utils import detect_device

redirect_bp = Blueprint("redirect", __name__)


def _standalone_page(title, body, max_width=420):
    """A small self-contained page for the phone that scanned the code.

    It cannot rely on the app stylesheet (the scanned link may open on a
    different origin), so it repeats the semantic colors. Callers must
    escape anything that came from a scanned QR.
    """
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} — DRQR</title>
</head>
<body style="margin:0;min-height:100vh;box-sizing:border-box;padding:24px;display:flex;align-items:center;justify-content:center;background:#0E0F11;color:#ECEBE8;font-family:Inter,system-ui,sans-serif">
<main style="width:100%;max-width:{max_width}px;box-sizing:border-box;background:#16181B;border:1px solid #2A2D32;border-radius:16px;padding:32px">
{body}
<p style="margin:20px 0 0;font-size:12px;color:#9A9A95">Secured by DRQR</p>
</main>
</body>
</html>"""


def _password_page(error=False):
    message = ('<p role="alert" style="margin:10px 0 0;font-size:13px;'
               'color:#FF6B5E">Incorrect password — try again</p>') if error else ""
    body = f"""
<h1 style="margin:0 0 8px;font-family:'Space Grotesk',Inter,sans-serif;font-size:24px;letter-spacing:-.02em;color:#D9F26B">Password protected</h1>
<p style="margin:0;font-size:14px;color:#9A9A95">This QR is protected by <b style="color:#ECEBE8">DRQR</b>.</p>
{message}
<form method="POST" style="margin-top:16px">
  <label for="pwd" style="display:block;margin-bottom:6px;font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#9A9A95">Password</label>
  <input id="pwd" name="pwd" type="password" placeholder="Enter password" required autocomplete="current-password" style="width:100%;box-sizing:border-box;padding:12px 14px;margin-bottom:12px;border:1px solid #5E646E;border-radius:10px;background:#1D2024;color:#ECEBE8;font-size:14px;outline:none">
  <button type="submit" style="width:100%;padding:12px 14px;border:1px solid #D9F26B;border-radius:10px;background:#D9F26B;color:#0E0F11;font-size:14px;font-weight:700;cursor:pointer">Unlock</button>
</form>
"""
    return _standalone_page("Password protected", body)


@redirect_bp.route("/r/<code>", methods=["GET", "POST"])
def redirect_dynamic(code):
    s = get_session()
    _qr = qr_repo.get_by_short(s, code)
    # Server-side only: the decision must be able to verify password_hash.
    row = qr_repo.to_internal(_qr) if _qr is not None else None
    # Password attempt — POST only to avoid URL leak (+ API header alt).
    # Expiry/limit/password/smart-url decisions live in app/services/redirect_service.
    ua0=request.headers.get("User-Agent","")
    accept0=request.headers.get("Accept-Language","")
    pwd = None
    if row and row["has_password"]:
        if request.method == "POST":
            pwd = request.form.get("pwd") or request.form.get("password")
        # Also check Authorization header as alternative (for API)
        if not pwd:
            auth_pwd = request.headers.get("X-QR-Password")
            if auth_pwd:
                pwd = auth_pwd
    decision = redirect_service.decide(row, pwd, ua0, accept0)
    if decision["action"] == "missing":
        s.close()
        return "QR not found or expired",404

    # Phase 10: a review QR serves a capture form instead of redirecting.
    # The customer submits, the review is stored, and only then are they sent
    # on to the configured destination.
    if row and row["type"] == "review" and decision["action"] == "ok":
        s.close()
        from flask import render_template_string
        import os as _os
        tpl = _os.path.join(_os.path.dirname(__file__), "..", "templates", "review_form.html")
        with open(tpl, encoding="utf-8") as f:
            return render_template_string(f.read(), short_code=row["short_code"])
    if decision["action"] == "gone":
        s.close()
        return decision["message"],410
    if decision["action"] == "password":
        if request.method == "POST":
            # Wrong password — show form with error
            s.close()
            return _password_page(error=True), 401
        s.close()
        return _password_page(error=False), 401
    # Track scan: fast local write now, geo enriched async after redirect.
    # Never block the redirect on external geo-IP HTTP calls.
    target, smart = decision["target"], decision["smart"]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    ua=request.headers.get("User-Agent","")
    device,browser,os_name=detect_device(ua)
    now=datetime.datetime.utcnow().isoformat()
    # Pending geo: enriched in background AFTER the redirect (see below).
    scan_id = scans_repo.record_scan(s, row["id"], now, ip, ua, device, browser, os_name)
    if smart:
        logger.info("Smart URL resolved for %s -> %s (device=%s)", code, target, device)
    s.close()
    if scan_id is not None:
        try:
            enrich_scan_geo(scan_id, ip)
        except Exception as e:
            logger.warning("Failed to queue geo enrichment: %s", e)
    country = "Pending"
    if target.startswith("http"):
        return flask_redirect(target, code=302)
    # Non-URL payloads (text, tel:, mailto:, Wi-Fi, …): show the decoded
    # content. It is user-controlled, so escape it before putting it in HTML.
    body = f"""
<h1 style="margin:0 0 8px;font-family:'Space Grotesk',Inter,sans-serif;font-size:24px;letter-spacing:-.02em">QR content</h1>
<p style="margin:0 0 16px;font-size:13px;color:#9A9A95">Scanned via DRQR dynamic QR</p>
<pre style="margin:0;white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;background:#1D2024;border:1px solid #2A2D32;border-radius:10px;color:#ECEBE8;font-family:'JetBrains Mono',monospace;font-size:13px">{escape(target[:2000])}</pre>
<p style="margin:16px 0 0;font-size:12px;color:#9A9A95">{escape(device)} • {escape(browser)} • {escape(country)}</p>
"""
    return _standalone_page("QR content", body, max_width=640)

"""The dynamic QR redirect: expiry, scan limit, password gate, smart-URL routing, scan tracking."""

import datetime

from flask import Blueprint, redirect as flask_redirect, request

from app.config import logger
from app.extensions import get_session
from app.repositories import qr_repo, scans_repo
from app.services import redirect_service
from app.services.geo import enrich_scan_geo
from app.utils import detect_device

redirect_bp = Blueprint("redirect", __name__)


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
    if decision["action"] == "gone":
        s.close()
        return decision["message"],410
    if decision["action"] == "password":
        if request.method == "POST":
            # Wrong password — show form with error
            s.close()
            return """
                <html style="font-family:Inter,sans-serif;background:#0A0A0A;color:white;display:flex;align-items:center;justify-content:center;min-height:100vh">
                <div style="background:#111;border:1px solid #222;padding:40px;border-radius:24px;max-width:400px;width:100%;text-align:center">
                <h2 style="color:#00FF88">ðŸ”’ Password Protected</h2>
                <p>This QR is protected by <b>NARE & CO.</b></p>
                <p style="color:#FF5555;font-size:13px;margin-top:8px">Incorrect password â€” try again</p>
                <form method="POST">
                  <input name="pwd" type="password" placeholder="Enter password" required style="width:100%;padding:14px;border-radius:12px;border:1px solid #333;background:#000;color:white;margin:16px 0"/>
                  <button type="submit" style="width:100%;padding:14px;background:#00FF88;color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer">Unlock</button>
                </form>
                <p style="font-size:12px;color:#888;margin-top:12px">Secured by NARE & CO. â€¢ Grid White / Black / Neon Green</p>
                </div></html>
                """,401
        s.close()
        return """
            <html style="font-family:Inter,sans-serif;background:#0A0A0A;color:white;display:flex;align-items:center;justify-content:center;min-height:100vh">
            <div style="background:#111;border:1px solid #222;padding:40px;border-radius:24px;max-width:400px;width:100%;text-align:center">
            <h2 style="color:#00FF88">ðŸ”’ Password Protected</h2>
            <p>This QR is protected by <b>NARE & CO.</b></p>
            <form method="POST">
              <input name="pwd" type="password" placeholder="Enter password" required style="width:100%;padding:14px;border-radius:12px;border:1px solid #333;background:#000;color:white;margin:16px 0"/>
              <button type="submit" style="width:100%;padding:14px;background:#00FF88;color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer">Unlock</button>
            </form>
            <p style="font-size:12px;color:#888;margin-top:12px">Secured by NARE & CO. â€¢ Grid White / Black / Neon Green â€¢ POST only, not logged in URL</p>
            </div></html>
            """,401
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
        logger.info(f"Smart URL resolved for {code} -> {target} (device={device})")
    s.close()
    if scan_id is not None:
        try:
            enrich_scan_geo(scan_id, ip)
        except Exception as e:
            logger.warning(f"Failed to queue geo enrichment: {e}")
    country = "Pending"
    if target.startswith("http"):
        return flask_redirect(target, code=302)
    else:
        return f"""
        <html style="font-family:Inter,sans-serif;background:#F8F9FA;min-height:100vh"><body style="margin:0;padding:40px;background:
        radial-gradient(circle at 1px 1px, #e5e7eb 1px, transparent 0);background-size:22px 22px">
        <div style="max-width:640px;margin:0 auto;background:white;border:1px solid #0A0A0A;border-radius:20px;overflow:hidden;box-shadow:8px 8px 0 #0A0A0A">
        <div style="background:#0A0A0A;color:#00FF88;padding:16px 24px;display:flex;justify-content:space-between;align-items:center"><b>NARE & CO.</b><span style="font-size:12px;border:1px solid #00FF88;padding:4px 8px;border-radius:20px">SECURE QR</span></div>
        <div style="padding:32px"><h2>QR Content</h2><pre style="white-space:pre-wrap;background:#F8F9FA;padding:16px;border-radius:12px;border:1px solid #e5e7eb">{target[:2000]}</pre>
        <p style="color:#666;font-size:13px">Scanned via NARE & CO. dynamic QR â€¢ {device} â€¢ {browser} â€¢ {country}</p></div></div></body></html>
        """

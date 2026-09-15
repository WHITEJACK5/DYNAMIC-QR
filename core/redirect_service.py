"""Redirect decision service: pure business logic for GET /r/<code> (Phase 2q).

Takes plain values (row dict, password attempt, UA strings, now) — no
Flask, no DB, no network. The handler maps decisions to HTTP; scanning,
logging, and enrichment stay in the handler. resolve_target is moved
verbatim from app.py with the Flask request replaced by two strings.
"""
import datetime
import json
import logging

from werkzeug.security import check_password_hash

from core.utils import detect_device

logger = logging.getLogger("nare")

SMART_TYPES = ("smarturl", "smart url", "multiurl")


def resolve_target(qr_row, user_agent="", accept_language="", country="unknown"):
    # Smart URL: data_json contains {"primaryUrl": "...", "rules": [{"condition":"android","url":"..."}]}
    # NOTE: country must be passed in — this function never does network I/O
    # itself, so the redirect path stays fast. Geo enrichment happens async
    # after the redirect is sent.
    try:
        data = json.loads(qr_row["data_json"]) if qr_row["data_json"] else {}
    except Exception:
        data = {}
    primary = data.get("primaryUrl") or data.get("url") or qr_row["content"]
    rules = data.get("rules")
    if isinstance(rules, str):
        # try parse lines like "device:android -> https://..."
        parsed = []
        for line in rules.splitlines():
            if "->" in line or "→" in line:
                sep = "->" if "->" in line else "→"
                cond, url = line.split(sep, 1)
                parsed.append({"condition": cond.strip().lower(), "url": url.strip()})
        rules = parsed
    if not isinstance(rules, list):
        return primary
    # detect — UA + Accept-Language only, no network
    ua = (user_agent or "").lower()
    device, browser, os_name = detect_device(ua)
    country = (country or "unknown").lower()
    # evaluate rules in order — flexible matching for personal use
    for rule in rules:
        cond = (rule.get("condition") or "").lower().strip()
        url = rule.get("url")
        if not cond or not url:
            continue
        # exact device match
        if cond in ("android", "ios", "mobile", "desktop"):
            # android/ios can be either device or OS
            if cond == "android" and "android" in os_name.lower():
                return url
            if cond == "ios" and "ios" in os_name.lower():
                return url
            if cond == device.lower():
                return url
        if cond.startswith("device:"):
            want = cond.split(":", 1)[1].strip().lower()
            if want == device.lower() or (want == "android" and "android" in os_name.lower()) or (want == "ios" and "ios" in os_name.lower()):
                return url
            if want in ua.lower():
                return url
        if cond.startswith("os:"):
            want = cond.split(":", 1)[1].strip().lower()
            if want in os_name.lower() or want in ua.lower():
                return url
        if cond.startswith("browser:"):
            want = cond.split(":", 1)[1].strip().lower()
            if want in browser.lower() or want in ua.lower():
                return url
        if cond.startswith("country:"):
            want = cond.split(":", 1)[1].strip().lower()
            if want == country.lower():
                return url
        if cond.startswith("lang:"):
            lang = cond.split(":", 1)[1].strip().lower()
            if lang in (accept_language or "").lower():
                return url
        # direct contains check (e.g., "android" in UA)
        if cond in ua.lower():
            return url
    return primary


def decide(row, password_attempt, user_agent="", accept_language="", now=None):
    """Return a decision dict. Actions: missing/gone/password/ok.

    - missing -> 404 "QR not found or expired"
    - gone -> 410 with message (expired / scan limit)
    - password -> 401 form (handler keys the error variant on POST, like legacy)
    - ok -> {"target", "smart"}; target is the redirect/content payload
    Unparseable expiry is ignored (legacy behavior), never a 500.
    """
    now = now or datetime.datetime.utcnow()
    if not row:
        return {"action": "missing"}
    row = dict(row)
    if row.get("expiry_date"):
        try:
            if now > datetime.datetime.fromisoformat(row["expiry_date"]):
                return {"action": "gone", "message": "This QR has expired"}
        except Exception as e:
            logger.warning(f"Expiry parse failed: {e}")
    if row.get("scan_limit") and (row.get("scan_count") or 0) >= row["scan_limit"]:
        return {"action": "gone", "message": "Scan limit reached"}
    if row.get("has_password"):
        if not password_attempt or not check_password_hash(row["password_hash"], password_attempt):
            return {"action": "password"}
    target, smart = row["content"], False
    if row.get("type") in SMART_TYPES and row.get("is_dynamic"):
        try:
            resolved = resolve_target(row, user_agent, accept_language)
            if resolved and resolved != target:
                target, smart = resolved, True
        except Exception as e:
            logger.warning(f"Smart resolve failed: {e}")
    return {"action": "ok", "target": target, "smart": smart}

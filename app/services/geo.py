"""Geo-IP enrichment (Phase 1e: never on the redirect path).

The lookup does two chained external HTTP calls, so it runs only in a
background job (app.jobs -> RQ or a thread). The redirect records a "Pending"
scan and returns immediately; this module fills in country/city afterwards.
"""

import requests

from app.config import logger as _logger
from app.jobs import enqueue_call
from app.repositories import scans_repo


def get_geo_from_ip(ip):
    """Best-effort country/city. Never raises; returns Unknown on failure."""
    logger = _logger
    if not ip or ip in ("127.0.0.1", "::1") or ip.startswith("192.168.") \
            or ip.startswith("10.") or ip.startswith("172."):
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                if 16 <= second <= 31:
                    return {"country": "Local", "city": "Local"}
            except Exception:
                pass
        if ip.startswith("192.168.") or ip.startswith("10.") or ip in ("127.0.0.1", "::1"):
            return {"country": "Local", "city": "Local"}
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city,status", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {"country": data.get("country", "Unknown"), "city": data.get("city", "Unknown")}
    except Exception as e:
        logger.debug("Geo lookup failed for %s: %s", ip, e)
    try:
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return {"country": data.get("country_name", "Unknown"), "city": data.get("city", "Unknown")}
    except Exception as e:
        logger.debug("Geo fallback failed for %s: %s", ip, e)
    return {"country": "Unknown", "city": "Unknown"}


def geo_enrich_job(scan_id, ip):
    """Module-level so RQ workers can import it (never enqueue a closure)."""
    from app.extensions import get_session

    try:
        geo = get_geo_from_ip(ip)
        s = get_session()
        try:
            scans_repo.update_geo(
                s, scan_id, geo.get("country", "Unknown"), geo.get("city", "Unknown")
            )
        finally:
            s.close()
    except Exception as e:
        _logger.warning("Async geo enrichment failed for scan %s: %s", scan_id, e)


def enrich_scan_geo(scan_id, ip):
    """Queue enrichment; returns 'rq' or 'thread'. Never blocks the response."""
    return enqueue_call(geo_enrich_job, scan_id, ip)

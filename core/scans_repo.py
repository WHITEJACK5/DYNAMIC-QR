"""Scans repository on the ORM (Phase 3c3) — dialect-agnostic.

Takes a SQLAlchemy Session. Never raises on writes (logs + returns None,
same as the legacy inline code); aggregates return plain dicts. Ownership
scoping for the per-QR detail stays with the caller via qr_repo.get_owned.
"""
import logging

from sqlalchemy import String, cast, func

from core.models import QRCode, Scan

logger = logging.getLogger("nare")


def record_scan(s, qr_id, timestamp, ip, user_agent, device, browser, os_name):
    """Insert a Pending scan + bump scan_count. Returns scan id or None."""
    try:
        scan = Scan(qr_id=qr_id, timestamp=timestamp, ip=ip, user_agent=user_agent,
                    device=device, browser=browser, os=os_name,
                    country="Pending", city="Pending")
        s.add(scan)
        qr = s.get(QRCode, qr_id)
        if qr is not None:
            qr.scan_count = (qr.scan_count or 0) + 1
            qr.updated_at = timestamp
        s.commit()
        return scan.id
    except Exception as e:
        logger.exception(f"Scan track failed: {e}")
        try:
            s.rollback()
        except Exception:  # nosec B110
            # Best-effort rollback only; the original error is logged above.
            pass
        return None


def update_geo(s, scan_id, country, city):
    try:
        scan = s.get(Scan, scan_id)
        if scan is not None:
            scan.country = country
            scan.city = city
            s.commit()
    except Exception as e:
        logger.warning(f"Geo update failed for scan {scan_id}: {e}")


def _owned_scan_ids(s, user_id):
    return [q.id for q in s.query(QRCode.id).filter(QRCode.user_id == user_id).all()]


def overview_for_user(s, user_id):
    qr_stats = s.query(
        func.count(QRCode.id), func.coalesce(func.sum(QRCode.scan_count), 0)
    ).filter(QRCode.user_id == user_id).one()
    ids = _owned_scan_ids(s, user_id)
    timeline, devices, countries = [], [], []
    if ids:
        # cast(...): SQLite's date() returns TEXT, PostgreSQL's returns a
        # date object — cast so both dialects hand the API a plain string.
        day = func.date(Scan.timestamp)
        timeline = [
            {"d": d, "c": c}
            for d, c in s.query(cast(day, String), func.count(Scan.id))
            .filter(Scan.qr_id.in_(ids))
            .group_by(day)
            .order_by(day.desc())
            .limit(14).all()
        ]
        devices = [
            {"device": d, "c": c}
            for d, c in s.query(Scan.device, func.count(Scan.id))
            .filter(Scan.qr_id.in_(ids)).group_by(Scan.device).all()
        ]
        countries = [
            {"country": c0, "c": c}
            for c0, c in s.query(Scan.country, func.count(Scan.id))
            .filter(Scan.qr_id.in_(ids)).group_by(Scan.country).all()
        ]
    top = [
        {"id": q.id, "name": q.name, "type": q.type, "scan_count": q.scan_count}
        for q in s.query(QRCode).filter(QRCode.user_id == user_id)
        .order_by(QRCode.scan_count.desc()).limit(10).all()
    ]
    return {
        "total_qrs": qr_stats[0] or 0,
        "total_scans": qr_stats[1] or 0,
        "timeline": timeline,
        "devices": devices,
        "countries": countries,
        "top": top,
    }


def detail_for_qr(s, qr_id):
    scans = [
        {
            "id": x.id, "qr_id": x.qr_id, "timestamp": x.timestamp, "ip": x.ip,
            "user_agent": x.user_agent, "device": x.device, "browser": x.browser,
            "os": x.os, "country": x.country, "city": x.city,
        }
        for x in s.query(Scan).filter(Scan.qr_id == qr_id)
        .order_by(Scan.timestamp.desc()).limit(100).all()
    ]
    devices = [
        {"device": d, "c": c}
        for d, c in s.query(Scan.device, func.count(Scan.id))
        .filter(Scan.qr_id == qr_id).group_by(Scan.device).all()
    ]
    countries = [
        {"country": c0, "c": c}
        for c0, c in s.query(Scan.country, func.count(Scan.id))
        .filter(Scan.qr_id == qr_id).group_by(Scan.country).all()
    ]
    day = func.date(Scan.timestamp)
    timeline = [
        {"d": d, "c": c}
        for d, c in s.query(cast(day, String), func.count(Scan.id))
        .filter(Scan.qr_id == qr_id)
        .group_by(day)
        .order_by(day).all()
    ]
    return {"scans": scans, "devices": devices, "countries": countries, "timeline": timeline}

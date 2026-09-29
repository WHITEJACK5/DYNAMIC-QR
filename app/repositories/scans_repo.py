"""Scans repository on the ORM (Phase 3c3) — dialect-agnostic.

Takes a SQLAlchemy Session. Never raises on writes (logs + returns None,
same as the legacy inline code); aggregates return plain dicts. Ownership
scoping for the per-QR detail stays with the caller via qr_repo.get_owned.
"""
import logging

from sqlalchemy import String, cast, func

from app.models import QRCode, Scan

logger = logging.getLogger("nare")


def record_scan(s, qr_id, timestamp, ip, user_agent, device, browser, os_name):
    """Insert a Pending scan and bump scan_count in one transaction.

    The increment is a single SQL UPDATE ... SET scan_count = scan_count + 1,
    not an ORM read-modify-write. The previous form loaded the row, added one
    in Python and wrote it back, so two concurrent scans of the same code
    both read 5 and both wrote 6, losing an increment — the count silently
    under-reports, which is the one number the product is sold on. The
    database evaluates the addition inside the statement, so concurrent
    writers serialise instead of overwriting. tests/test_concurrency.py
    proves this with real threads against PostgreSQL.
    """
    try:
        scan = Scan(qr_id=qr_id, timestamp=timestamp, ip=ip, user_agent=user_agent,
                    device=device, browser=browser, os=os_name,
                    country="Pending", city="Pending")
        s.add(scan)
        s.flush()
        s.query(QRCode).filter(QRCode.id == qr_id).update(
            {
                QRCode.scan_count: func.coalesce(QRCode.scan_count, 0) + 1,
                QRCode.updated_at: timestamp,
            },
            synchronize_session=False,
        )
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


def detail_for_qr(s, qr_id, limit=None, offset=0):
    """Per-QR analytics: a paginated scan list plus the aggregates.

    The scan list used to be a hardcoded `.limit(100)`, which is truncation
    rather than pagination: scans 101+ were unreachable with no `total` to
    say so. The directive asks for limit/offset on any list endpoint, so the
    window is now the caller's and the true count is always returned.
    """
    base = s.query(Scan).filter(Scan.qr_id == qr_id)
    total = base.count()
    if limit is not None:
        base = base.order_by(Scan.timestamp.desc()).limit(limit).offset(offset)
    else:
        base = base.order_by(Scan.timestamp.desc())
    scans = [
        {
            "id": x.id, "qr_id": x.qr_id, "timestamp": x.timestamp, "ip": x.ip,
            "user_agent": x.user_agent, "device": x.device, "browser": x.browser,
            "os": x.os, "country": x.country, "city": x.city,
        }
        for x in base.all()
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
    return {"scans": scans, "devices": devices, "countries": countries,
            "timeline": timeline, "total": total, "total_scans": total,
            "limit": limit, "offset": offset}

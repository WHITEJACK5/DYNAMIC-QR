"""Scans repository: scan writes + analytics aggregates (Phase 2n).

Never raises on writes (logs + returns None, same as the legacy inline
code); aggregates return plain dicts/lists. Ownership scoping for the
per-QR detail stays with the caller via qr_repo.get_owned.
"""
import logging

logger = logging.getLogger("nare")


def record_scan(db, qr_id, timestamp, ip, user_agent, device, browser, os_name):
    """Insert a Pending scan + bump scan_count. Returns scan id or None."""
    try:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO scans (qr_id,timestamp,ip,user_agent,device,browser,os,country,city)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (qr_id, timestamp, ip, user_agent, device, browser, os_name, "Pending", "Pending"),
        )
        scan_id = cur.lastrowid
        cur.execute(
            "UPDATE qrcodes SET scan_count=scan_count+1, updated_at=? WHERE id=?",
            (timestamp, qr_id),
        )
        db.commit()
        return scan_id
    except Exception as e:
        logger.exception(f"Scan track failed: {e}")
        try:
            db.rollback()
        except Exception:  # nosec B110
            # Best-effort rollback only; the original error is logged above.
            pass
        return None


def update_geo(db, scan_id, country, city):
    try:
        cur = db.cursor()
        cur.execute(
            "UPDATE scans SET country=?, city=? WHERE id=?", (country, city, scan_id)
        )
        db.commit()
    except Exception as e:
        logger.warning(f"Geo update failed for scan {scan_id}: {e}")


def overview_for_user(db, user_id):
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) as total, SUM(scan_count) as scans FROM qrcodes WHERE user_id=?",
        (user_id,),
    )
    row = cur.fetchone()
    cur.execute(
        "SELECT date(timestamp) as d, COUNT(*) as c FROM scans WHERE qr_id IN"
        " (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY date(timestamp)"
        " ORDER BY d DESC LIMIT 14",
        (user_id,),
    )
    timeline = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT device, COUNT(*) as c FROM scans WHERE qr_id IN"
        " (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY device",
        (user_id,),
    )
    devices = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT country, COUNT(*) as c FROM scans WHERE qr_id IN"
        " (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY country",
        (user_id,),
    )
    countries = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT id,name,type,scan_count FROM qrcodes WHERE user_id=?"
        " ORDER BY scan_count DESC LIMIT 10",
        (user_id,),
    )
    top = [dict(r) for r in cur.fetchall()]
    return {
        "total_qrs": row["total"] or 0,
        "total_scans": row["scans"] or 0,
        "timeline": timeline,
        "devices": devices,
        "countries": countries,
        "top": top,
    }


def detail_for_qr(db, qr_id):
    cur = db.cursor()
    cur.execute("SELECT * FROM scans WHERE qr_id=? ORDER BY timestamp DESC LIMIT 100", (qr_id,))
    scans = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT device, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY device", (qr_id,))
    devices = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT country, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY country", (qr_id,))
    countries = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT date(timestamp) as d, COUNT(*) as c FROM scans WHERE qr_id=?"
        " GROUP BY date(timestamp) ORDER BY d",
        (qr_id,),
    )
    timeline = [dict(r) for r in cur.fetchall()]
    return {"scans": scans, "devices": devices, "countries": countries, "timeline": timeline}

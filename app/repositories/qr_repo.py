"""QR-code repository on the ORM (Phase 3c2) — dialect-agnostic.

Takes a SQLAlchemy Session. Every public function returns plain dicts (via
to_public) so handlers keep the exact shapes they had against
sqlite3.Row. Column writes go through an allowlist; nothing user-supplied
reaches a query.
"""
import datetime
import json
import logging

from sqlalchemy import func
from werkzeug.security import generate_password_hash

from app.models import QRCode, Scan
from app.utils import build_qr_content, generate_short_code

logger = logging.getLogger("nare")

#: Columns writable via PUT. Unknown keys are ignored, like the legacy loop.
UPDATABLE = (
    "name", "type", "content", "data_json", "fg_color", "bg_color",
    "gradient", "pattern", "eye_style", "frame_text", "frame_color",
    "folder_id", "expiry_date", "scan_limit",
)

#: Columns create_full accepts. Anything else is rejected loudly.
CREATABLE = (
    "user_id", "folder_id", "name", "type", "content", "data_json",
    "is_dynamic", "short_code", "fg_color", "bg_color", "gradient",
    "pattern", "eye_style", "frame_text", "frame_color", "logo_path",
    "has_password", "password_hash", "expiry_date", "scan_limit",
    "scan_count",
)

ORDER_NEWEST_FIRST = (QRCode.created_at.desc(), QRCode.id.desc())


def to_public(qr):
    """Domain-safe dict: no password hash, logo path collapsed to a flag."""
    d = {
        c.name: getattr(qr, c.name)
        for c in QRCode.__table__.columns
    }
    d.pop("password_hash", None)
    # Don't expose absolute logo_path; give relative if needed
    if d.get("logo_path"):
        d["has_logo"] = True
    return d


def to_internal(qr):
    """Full row including password_hash — server-side only.

    Used by the redirect decision, which must verify a QR's password.
    Never send this to a client; to_public() is for API responses.
    """
    return {c.name: getattr(qr, c.name) for c in QRCode.__table__.columns}


def count_owned(s, user_id):
    return s.query(func.count(QRCode.id)).filter(QRCode.user_id == user_id).scalar()


def list_owned(s, user_id, limit=None, offset=None):
    q = s.query(QRCode).filter(QRCode.user_id == user_id).order_by(*ORDER_NEWEST_FIRST)
    if limit is not None:
        q = q.limit(limit).offset(offset or 0)
    return q.all()


def get_owned(s, qr_id, user_id):
    return s.query(QRCode).filter(QRCode.id == qr_id, QRCode.user_id == user_id).one_or_none()


def get_by_short(s, code):
    return s.query(QRCode).filter(QRCode.short_code == code).one_or_none()


def delete_owned(s, qr_id, user_id):
    """Delete QR + its scans. False when not found; raises on DB error."""
    qr = get_owned(s, qr_id, user_id)
    if qr is None:
        return False
    s.query(Scan).filter(Scan.qr_id == qr_id).delete(synchronize_session=False)
    s.delete(qr)
    s.commit()
    return True


def mint_unique_short(s, tries=10):
    """Unused-short_code, falling back to a fresh unchecked code."""
    for _ in range(tries):
        cand = generate_short_code(8)
        try:
            if s.query(QRCode.id).filter(QRCode.short_code == cand).scalar() is None:
                return cand
        except Exception as e:
            logger.warning(f"short_code check failed: {e}")
            break
    return generate_short_code(8)


def create_full(s, **fields):
    """Insert one QR row. Commits; returns id. Raises IntegrityError on collision."""
    unknown = [k for k in fields if k not in CREATABLE]
    if unknown:
        raise ValueError(f"Unknown columns: {unknown}")
    now = datetime.datetime.utcnow().isoformat()
    values = {
        "folder_id": None, "gradient": None, "frame_text": None,
        "frame_color": None, "logo_path": None,
        "pattern": "square", "eye_style": "square",
        "has_password": 0, "password_hash": None, "expiry_date": None,
        "scan_limit": None, "scan_count": 0, "created_at": now, "updated_at": now,
    }
    values.update(fields)
    qr = QRCode(**values)
    s.add(qr)
    s.commit()
    return qr.id


def apply_update(s, qr_id, user_id, body):
    """Apply a schema-validated PUT body. Returns public dict, None if missing."""
    qr = get_owned(s, qr_id, user_id)
    if qr is None:
        return None
    for f in UPDATABLE:
        if f in body:
            setattr(qr, f, body[f] if f != "data_json" or isinstance(body[f], str)
                    else json.dumps(body[f]))
    if "password" in body:
        if body["password"]:
            qr.has_password = 1
            qr.password_hash = generate_password_hash(body["password"])
        else:
            qr.has_password = 0
            qr.password_hash = None
    if "scan_limit" in body:
        sl = body["scan_limit"]
        qr.scan_limit = int(sl) if sl is not None else None
    if "data" in body:
        qr.content = build_qr_content(body.get("type", qr.type), body["data"])
        qr.data_json = json.dumps(body["data"])
    qr.updated_at = datetime.datetime.utcnow().isoformat()
    s.commit()
    s.refresh(qr)
    return to_public(qr)


def duplicate_owned(s, qr_id, user_id):
    """Copy own QR (scan_count reset, new short_code when dynamic)."""
    qr = get_owned(s, qr_id, user_id)
    if qr is None:
        return None
    now = datetime.datetime.utcnow().isoformat()
    new_code = mint_unique_short(s, 5) if qr.is_dynamic else None
    copy = QRCode(
        user_id=user_id, folder_id=qr.folder_id, name=qr.name + " (Copy)",
        type=qr.type, content=qr.content, data_json=qr.data_json,
        is_dynamic=qr.is_dynamic, short_code=new_code, fg_color=qr.fg_color,
        bg_color=qr.bg_color, gradient=qr.gradient, pattern=qr.pattern,
        eye_style=qr.eye_style, frame_text=qr.frame_text,
        frame_color=qr.frame_color, logo_path=qr.logo_path,
        has_password=qr.has_password, password_hash=qr.password_hash,
        expiry_date=qr.expiry_date, scan_limit=qr.scan_limit, scan_count=0,
        created_at=now, updated_at=now,
    )
    s.add(copy)
    s.commit()
    return copy.id

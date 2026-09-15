"""QR-code repository: all qrcodes-table SQL, always user-scoped (Phase 2l/2n2).

First slices: single-QR read/write, then create/duplicate. Handlers keep
HTTP concerns (auth, schemas, images, status codes); every INSERT/SELECT/
UPDATE/DELETE on qrcodes lives here. Takes a plain sqlite3 connection (Row
factory, as returned by app.get_db) so it is testable without Flask.
Hashing/content helpers are concrete imports for now; the services slice
will inject them.
"""
import datetime
import json
import logging

from werkzeug.security import generate_password_hash

from core.utils import build_qr_content, generate_short_code

logger = logging.getLogger("nare")

#: Columns writable via PUT (unknown keys ignored, like the legacy loop).
UPDATABLE = (
    "name", "type", "content", "data_json", "fg_color", "bg_color",
    "gradient", "pattern", "eye_style", "frame_text", "frame_color",
    "folder_id", "has_password", "password_hash", "expiry_date", "scan_limit",
)


def to_public(row):
    """Domain-safe dict: no password hash, logo path collapsed to a flag."""
    d = dict(row)
    d.pop("password_hash", None)
    # Don't expose absolute logo_path; give relative if needed
    if d.get("logo_path"):
        d["has_logo"] = True
    return d


def count_owned(db, user_id):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM qrcodes WHERE user_id=?", (user_id,))
    return cur.fetchone()[0]


def list_owned(db, user_id, limit=None, offset=None):
    cur = db.cursor()
    if limit is None:
        cur.execute(
            "SELECT * FROM qrcodes WHERE user_id=? ORDER BY created_at DESC, id DESC",
            (user_id,),
        )
    else:
        cur.execute(
            "SELECT * FROM qrcodes WHERE user_id=? ORDER BY created_at DESC, id DESC"
            " LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    return cur.fetchall()


def get_owned(db, qr_id, user_id):
    cur = db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id, user_id))
    return cur.fetchone()


def get_by_short(db, code):
    cur = db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE short_code=?", (code,))
    return cur.fetchone()


def delete_owned(db, qr_id, user_id):
    """Delete QR + its scans. Returns False when not found; raises on SQL error."""
    cur = db.cursor()
    cur.execute("SELECT scan_count FROM qrcodes WHERE id=? AND user_id=?", (qr_id, user_id))
    if not cur.fetchone():
        return False
    cur.execute("DELETE FROM qrcodes WHERE id=? AND user_id=?", (qr_id, user_id))
    cur.execute("DELETE FROM scans WHERE qr_id=?", (qr_id,))
    db.commit()
    return True


def apply_update(db, qr_id, user_id, body):
    """Apply a schema-validated PUT body. Returns public dict, None if missing.

    Unknown keys are ignored (QRUpdateRequest uses extra="ignore"), matching
    the legacy allowlist loop. Propagates SQL errors to the caller, which
    maps them to 500.
    """
    cur = db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id, user_id))
    row = cur.fetchone()
    if not row:
        return None
    fields, vals = [], []
    for f in UPDATABLE:
        if f in ("has_password", "password_hash", "expiry_date", "scan_limit"):
            continue  # handled below with their own semantics
        if f in body:
            fields.append(f"{f}=?")
            vals.append(body[f] if f != "data_json" or isinstance(body[f], str) else json.dumps(body[f]))
    if "password" in body:
        if body["password"]:
            fields.append("has_password=1")
            fields.append("password_hash=?")
            vals.append(generate_password_hash(body["password"]))
        else:
            fields.append("has_password=0")
            fields.append("password_hash=NULL")
    if "expiry_date" in body:
        fields.append("expiry_date=?")
        vals.append(body["expiry_date"])
    if "scan_limit" in body:
        sl = body["scan_limit"]
        fields.append("scan_limit=?")
        vals.append(int(sl) if sl is not None else None)
    if "data" in body:
        fields.append("content=?")
        vals.append(build_qr_content(body.get("type", row["type"]), body["data"]))
        fields.append("data_json=?")
        vals.append(json.dumps(body["data"]))
    if fields:
        fields.append("updated_at=?")
        vals.append(datetime.datetime.utcnow().isoformat())
        vals.extend([qr_id, user_id])
        # Column names come only from the hardcoded allowlist above (never
        # raw user input); all values use ? placeholders.
        cur.execute(f"UPDATE qrcodes SET {', '.join(fields)} WHERE id=? AND user_id=?", vals)  # nosec B608
        db.commit()
    cur.execute("SELECT * FROM qrcodes WHERE id=?", (qr_id,))
    return to_public(cur.fetchone())


def mint_unique_short(db, tries=10):
    """Unused-short_code, falling back to a fresh unchecked code."""
    cur = db.cursor()
    for _ in range(tries):
        cand = generate_short_code(8)
        try:
            cur.execute("SELECT id FROM qrcodes WHERE short_code=?", (cand,))
            if not cur.fetchone():
                return cand
        except Exception as e:
            logger.warning(f"short_code check failed: {e}")
            break
    return generate_short_code(8)


#: Full-column INSERT order shared by generate/bulk/duplicate.
CREATE_COLS = (
    "user_id", "folder_id", "name", "type", "content", "data_json",
    "is_dynamic", "short_code", "fg_color", "bg_color", "gradient",
    "pattern", "eye_style", "frame_text", "frame_color", "logo_path",
    "has_password", "password_hash", "expiry_date", "scan_limit",
    "scan_count", "created_at", "updated_at",
)


def create_full(db, **fields):
    """Insert one QR row. Commits; returns id. Raises IntegrityError on collision."""
    now = datetime.datetime.utcnow().isoformat()
    row = {
        "folder_id": None, "gradient": None, "frame_text": None,
        "frame_color": None, "logo_path": None,
        "pattern": "square", "eye_style": "square",
        "has_password": 0, "password_hash": None, "expiry_date": None,
        "scan_limit": None, "scan_count": 0, "created_at": now, "updated_at": now,
    }
    row.update(fields)
    unknown = [k for k in row if k not in CREATE_COLS]
    if unknown:
        raise ValueError(f"Unknown columns: {unknown}")
    cur = db.cursor()
    placeholders = ",".join("?" for _ in CREATE_COLS)
    cur.execute(
        f"INSERT INTO qrcodes ({','.join(CREATE_COLS)}) VALUES ({placeholders})",  # nosec B608 — cols constant
        tuple(row[c] for c in CREATE_COLS),
    )
    db.commit()
    return cur.lastrowid


def duplicate_owned(db, qr_id, user_id):
    """Copy own QR (scan_count reset). Returns new id, None if not found."""
    cur = db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id, user_id))
    row = cur.fetchone()
    if not row:
        return None
    new_code = mint_unique_short(db, 5) if row["is_dynamic"] else None
    now = datetime.datetime.utcnow().isoformat()
    return _duplicate_insert(db, user_id, dict(row), new_code, now)


def _duplicate_insert(db, user_id, src, new_code, now):
    cur = db.cursor()
    cur.execute(
        f"INSERT INTO qrcodes ({','.join(CREATE_COLS)}) VALUES ({','.join('?' for _ in CREATE_COLS)})",  # nosec B608 — cols constant
        (user_id, src["folder_id"], src["name"] + " (Copy)", src["type"], src["content"],
         src["data_json"], src["is_dynamic"], new_code, src["fg_color"], src["bg_color"],
         src["gradient"], src["pattern"], src["eye_style"], src["frame_text"],
         src["frame_color"], src["logo_path"], src["has_password"], src["password_hash"],
         src["expiry_date"], src["scan_limit"], 0, now, now),
    )
    db.commit()
    return cur.lastrowid

"""QR-code repository: all qrcodes-table SQL, always user-scoped (Phase 2l).

First slice of the backend split. Handlers keep HTTP concerns (auth,
pagination params, schemas, status codes); everything touching the
qrcodes/scans tables for single-QR read/write lives here. Takes a plain
sqlite3 connection (Row factory, as returned by app.get_db) so it is
testable without Flask. Hashing/content helpers are concrete imports for
now; the services slice will inject them.
"""
import datetime
import json
import logging

from werkzeug.security import generate_password_hash

from core.utils import build_qr_content

logger = logging.getLogger("nare")

ORDER = "ORDER BY created_at DESC, id DESC"

#: Columns writable via PUT (unknown keys are rejected, never interpolated).
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
        cur.execute(f"SELECT * FROM qrcodes WHERE user_id=? {ORDER}", (user_id,))
    else:
        cur.execute(
            f"SELECT * FROM qrcodes WHERE user_id=? {ORDER} LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    return cur.fetchall()


def get_owned(db, qr_id, user_id):
    cur = db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id, user_id))
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

"""Folders repository: user-scoped micro-CRUD (Phase 2m/2p)."""
import datetime


def count_for_user(db, user_id):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM folders WHERE user_id=?", (user_id,))
    return cur.fetchone()[0]


def list_for_user(db, user_id, limit=None, offset=None):
    cur = db.cursor()
    if limit is None:
        cur.execute("SELECT * FROM folders WHERE user_id=? ORDER BY id DESC", (user_id,))
    else:
        cur.execute(
            "SELECT * FROM folders WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    return [dict(r) for r in cur.fetchall()]


def create_for_user(db, user_id, name):
    cur = db.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO folders (user_id,name,created_at) VALUES (?,?,?)",
        (user_id, name, now),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name}

"""Folders repository: user-scoped micro-CRUD (Phase 2m)."""
import datetime


def list_for_user(db, user_id):
    cur = db.cursor()
    cur.execute("SELECT * FROM folders WHERE user_id=?", (user_id,))
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

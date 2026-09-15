"""Templates repository: user-scoped micro-CRUD (Phase 2m/2p)."""
import datetime
import json


def count_for_user(db, user_id):
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM templates WHERE user_id=?", (user_id,))
    return cur.fetchone()[0]


def list_for_user(db, user_id, limit=None, offset=None):
    cur = db.cursor()
    if limit is None:
        cur.execute("SELECT * FROM templates WHERE user_id=? ORDER BY id DESC", (user_id,))
    else:
        cur.execute(
            "SELECT * FROM templates WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
    return [dict(r) for r in cur.fetchall()]


def create_for_user(db, user_id, name, config):
    cur = db.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO templates (user_id,name,config_json,created_at) VALUES (?,?,?,?)",
        (user_id, name, json.dumps(config if config is not None else {}), now),
    )
    db.commit()
    return {"id": cur.lastrowid, "name": name}

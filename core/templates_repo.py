"""Templates repository: user-scoped micro-CRUD (Phase 2m)."""
import datetime
import json


def list_for_user(db, user_id):
    cur = db.cursor()
    cur.execute("SELECT * FROM templates WHERE user_id=?", (user_id,))
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

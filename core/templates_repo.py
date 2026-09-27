"""Templates repository on the ORM (Phase 3c1) — dialect-agnostic."""
import datetime
import json

from sqlalchemy import func

from core.models import Template


def count_for_user(s, user_id):
    return s.query(func.count(Template.id)).filter(Template.user_id == user_id).scalar()


def list_for_user(s, user_id, limit=None, offset=None):
    q = s.query(Template).filter(Template.user_id == user_id).order_by(Template.id.desc())
    if limit is not None:
        q = q.limit(limit).offset(offset or 0)
    return [
        {"id": t.id, "user_id": t.user_id, "name": t.name,
         "config_json": t.config_json, "created_at": t.created_at}
        for t in q.all()
    ]


def create_for_user(s, user_id, name, config):
    t = Template(user_id=user_id, name=name,
                 config_json=json.dumps(config if config is not None else {}),
                 created_at=datetime.datetime.utcnow().isoformat())
    s.add(t)
    s.commit()
    return {"id": t.id, "name": t.name}

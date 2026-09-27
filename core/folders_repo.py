"""Folders repository on the ORM (Phase 3c1) — dialect-agnostic."""
import datetime

from sqlalchemy import func

from core.models import Folder


def count_for_user(s, user_id):
    return s.query(func.count(Folder.id)).filter(Folder.user_id == user_id).scalar()


def list_for_user(s, user_id, limit=None, offset=None):
    q = s.query(Folder).filter(Folder.user_id == user_id).order_by(Folder.id.desc())
    if limit is not None:
        q = q.limit(limit).offset(offset or 0)
    return [
        {"id": f.id, "user_id": f.user_id, "name": f.name, "created_at": f.created_at}
        for f in q.all()
    ]


def create_for_user(s, user_id, name):
    f = Folder(user_id=user_id, name=name,
               created_at=datetime.datetime.utcnow().isoformat())
    s.add(f)
    s.commit()
    return {"id": f.id, "name": f.name}

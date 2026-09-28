"""Users repository on the ORM (Phase 3c1) — dialect-agnostic.

Takes a SQLAlchemy Session instead of a sqlite3 connection, so the same
code runs on PostgreSQL. Hashes stay opaque inputs; nothing here knows
about Flask.
"""
import datetime

from app.models import User


def find_id_by_email(s, email):
    return s.query(User.id).filter(User.email == email).scalar()


def find_by_email(s, email):
    """Returns a dict (not an ORM object) so handlers keep the same shape
    they had against sqlite3.Row."""
    u = s.query(User).filter(User.email == email).one_or_none()
    if u is None:
        return None
    return {
        "id": u.id, "email": u.email, "password_hash": u.password_hash,
        "name": u.name, "created_at": u.created_at,
        "twofa_enabled": u.twofa_enabled, "twofa_secret": u.twofa_secret,
        "is_premium": u.is_premium,
        "email_verified": bool(u.email_verified),
    }


def find_verify(s, email):
    """Verification state for a user, or None if there is no such user."""
    u = s.query(User).filter(User.email == email).one_or_none()
    if u is None:
        return None
    return {"email_verified": u.email_verified or 0,
            "verify_token": u.verify_token,
            "verify_expires": u.verify_expires}


def set_verify_token(s, email, token_hash, expires_iso):
    s.query(User).filter(User.email == email).update(
        {"verify_token": token_hash, "verify_expires": expires_iso}
    )
    s.commit()


def mark_email_verified(s, email):
    """Idempotent, and clears the token so a link cannot be replayed."""
    s.query(User).filter(User.email == email).update(
        {"email_verified": 1, "verify_token": None, "verify_expires": None}
    )
    s.commit()


def is_verified(s, user_id):
    u = s.get(User, user_id)
    if u is None:
        return False
    return bool(u.email_verified)


def find_public_by_id(s, user_id):
    u = s.get(User, user_id)
    if u is None:
        return None
    return {
        "id": u.id, "email": u.email, "name": u.name, "created_at": u.created_at,
        "is_premium": u.is_premium, "twofa_enabled": u.twofa_enabled,
        "email_verified": bool(u.email_verified),
    }


def create_user(s, email, password_hash, name):
    u = User(email=email, password_hash=password_hash, name=name,
             created_at=datetime.datetime.utcnow().isoformat())
    s.add(u)
    s.commit()
    return u.id


def set_reset_token(s, email, token_hash, expires_iso):
    s.query(User).filter(User.email == email).update(
        {"reset_token": token_hash, "reset_expires": expires_iso}
    )
    s.commit()


def find_reset(s, email):
    u = s.query(User).filter(User.email == email).one_or_none()
    if u is None:
        return None
    return {"reset_token": u.reset_token, "reset_expires": u.reset_expires}


def complete_reset(s, email, new_password_hash):
    s.query(User).filter(User.email == email).update(
        {"password_hash": new_password_hash, "reset_token": None, "reset_expires": None}
    )
    s.commit()


def get_2fa(s, user_id):
    u = s.get(User, user_id)
    if u is None:
        return None
    return {"twofa_secret": u.twofa_secret, "twofa_enabled": u.twofa_enabled}


def set_2fa_secret(s, user_id, secret):
    s.query(User).filter(User.id == user_id).update({"twofa_secret": secret})
    s.commit()


def set_2fa_enabled(s, user_id, enabled):
    s.query(User).filter(User.id == user_id).update(
        {"twofa_enabled": 1 if enabled else 0}
    )
    s.commit()


def clear_2fa(s, user_id):
    s.query(User).filter(User.id == user_id).update(
        {"twofa_enabled": 0, "twofa_secret": None}
    )
    s.commit()

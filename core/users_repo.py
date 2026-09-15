"""Users repository: all users-table SQL (Phase 2q2, last table standing).

Callers pass a plain sqlite3 connection; no Flask, no hashing (hashes are
computed by handlers/services and stored opaquely). Registration's default
folder stays orchestrated by the handler via folders_repo.
"""
import datetime


def find_id_by_email(db, email):
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    return row["id"] if row else None


def find_by_email(db, email):
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    return cur.fetchone()


def find_public_by_id(db, user_id):
    cur = db.cursor()
    cur.execute(
        "SELECT id,email,name,created_at,is_premium,twofa_enabled FROM users WHERE id=?",
        (user_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def create_user(db, email, password_hash, name):
    cur = db.cursor()
    now = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO users (email,password_hash,name,created_at) VALUES (?,?,?,?)",
        (email, password_hash, name, now),
    )
    db.commit()
    return cur.lastrowid


def set_reset_token(db, email, token_hash, expires_iso):
    cur = db.cursor()
    cur.execute(
        "UPDATE users SET reset_token=?, reset_expires=? WHERE email=?",
        (token_hash, expires_iso, email),
    )
    db.commit()


def find_reset(db, email):
    cur = db.cursor()
    cur.execute("SELECT reset_token, reset_expires FROM users WHERE email=?", (email,))
    return cur.fetchone()


def complete_reset(db, email, new_password_hash):
    cur = db.cursor()
    cur.execute(
        "UPDATE users SET password_hash=?, reset_token=NULL, reset_expires=NULL WHERE email=?",
        (new_password_hash, email),
    )
    db.commit()


def get_2fa(db, user_id):
    cur = db.cursor()
    cur.execute("SELECT twofa_secret, twofa_enabled FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def set_2fa_secret(db, user_id, secret):
    cur = db.cursor()
    cur.execute("UPDATE users SET twofa_secret=? WHERE id=?", (secret, user_id))
    db.commit()


def set_2fa_enabled(db, user_id, enabled):
    cur = db.cursor()
    cur.execute("UPDATE users SET twofa_enabled=? WHERE id=?", (1 if enabled else 0, user_id))
    db.commit()


def clear_2fa(db, user_id):
    cur = db.cursor()
    cur.execute("UPDATE users SET twofa_enabled=0, twofa_secret=NULL WHERE id=?", (user_id,))
    db.commit()

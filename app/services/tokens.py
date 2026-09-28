"""Auth token service: access/refresh JWTs and a revocation list (Phase 4c).

The directive requires short-lived (15 minute) access tokens, refresh
tokens, and a Redis-backed revocation list so a compromised token can be
invalidated before its natural expiry.

Design notes:

  * Access tokens live 15 minutes. They are self-contained, so validation is
    a signature check plus a revocation lookup — no database read per
    request, which matters on /r/<code>.
  * Refresh tokens live 30 days and are rotated on every use: the presented
    one is revoked as the replacement is issued, so a stolen refresh token
    is usable at most once.
  * Revocation is keyed by the JWT's own `jti` claim with a TTL equal to the
    token's remaining lifetime, so the denylist self-cleans and a revoked
    token cannot be un-revoked by a restart.
  * A `typ` claim keeps an access token from being presented at the refresh
    endpoint and vice versa.

Redis is the system of record for the denylist; an in-memory dict backs
single-process dev and tests. The trade-off is stated honestly: a Redis
flush un-revokes tokens, so the revocation keyspace must live in a
persistent Redis with an eviction policy that does not target it. This is
documented in the README rather than implied.
"""
import datetime
import logging
import secrets
import time

import jwt

from app import cache

logger = logging.getLogger("nare")

ACCESS_MINUTES = 15          # directive: short-lived access tokens
REFRESH_DAYS = 30
TEMP_TOKEN_MINUTES = 5       # 2FA pending, unchanged

ACCESS = "access"
REFRESH = "refresh"
TEMP = "temp"

_revoked = {}                # jti -> expires_at (in-process fallback)


def _now():
    return datetime.datetime.utcnow()


def _new_jti():
    return secrets.token_urlsafe(16)


def _encode(payload, secret, algo="HS256"):
    return jwt.encode(payload, secret, algorithm=algo)


def mint_access_token(user_id, email, secret, algo="HS256", minutes=ACCESS_MINUTES):
    """15-minute access token."""
    now = _now()
    return _encode({
        "user_id": user_id,
        "email": email,
        "typ": ACCESS,
        "jti": _new_jti(),
        "iat": now,
        "exp": now + datetime.timedelta(minutes=minutes),
    }, secret, algo)


def mint_refresh_token(user_id, email, secret, algo="HS256", days=REFRESH_DAYS):
    """Long-lived refresh token. Rotated on every use."""
    now = _now()
    return _encode({
        "user_id": user_id,
        "email": email,
        "typ": REFRESH,
        "jti": _new_jti(),
        "iat": now,
        "exp": now + datetime.timedelta(days=days),
    }, secret, algo)


def mint_temp_token(user_id, email, secret, algo="HS256", minutes=TEMP_TOKEN_MINUTES):
    """2FA pending token: proves credentials, grants nothing on its own."""
    now = _now()
    return _encode({
        "user_id": user_id,
        "email": email,
        "typ": TEMP,
        "jti": _new_jti(),
        "2fa_pending": True,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=minutes),
    }, secret, algo)


def mint_pair(user_id, email, secret, algo="HS256"):
    """The (access, refresh) tuple handed out by register/login."""
    return mint_access_token(user_id, email, secret, algo), \
        mint_refresh_token(user_id, email, secret, algo)


def decode(token, secret, algo="HS256"):
    """Return payload; raises jwt.ExpiredSignatureError / jwt.InvalidTokenError."""
    return jwt.decode(token, secret, algorithms=[algo])


# --------------------------------------------------------------------- revocation
def _key(jti):
    return f"revoked:{jti}"


def _seconds_left(exp):
    """Seconds until `exp`.

    PyJWT decodes `exp` to a POSIX timestamp, but a payload built in-process
    (tests, future callers) may carry a datetime, so both are accepted.
    """
    if isinstance(exp, datetime.datetime):
        return (exp - _now()).total_seconds()
    return float(exp) - time.time()


def revoke(payload):
    """Revoke a decoded token for exactly its remaining lifetime.

    Returns True if the token was still valid to revoke. A token that has
    already expired needs no entry — the signature check rejects it anyway.
    """
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or exp is None:
        return False
    ttl = int(_seconds_left(exp))
    if ttl <= 0:
        return False
    client = cache.get_redis()
    if client is not None:
        try:
            client.setex(_key(jti), ttl, "1")
            return True
        except Exception as e:
            logger.warning(f"Revocation Redis write failed, memory fallback: {e}")
    _revoked[jti] = time.time() + ttl
    return True


def is_revoked(jti):
    if not jti:
        return False
    client = cache.get_redis()
    if client is not None:
        try:
            return bool(client.exists(_key(jti)))
        except Exception as e:
            logger.warning(f"Revocation Redis read failed, memory fallback: {e}")
    exp = _revoked.get(jti)
    if exp is None:
        return False
    if exp < time.time():
        _revoked.pop(jti, None)
        return False
    return True


def reset_state():
    """Test hook: clear the in-process denylist."""
    _revoked.clear()

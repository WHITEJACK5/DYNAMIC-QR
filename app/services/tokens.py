"""Auth token service: single JWT mint/verify path (Phase 2q2).

Secret/algo are passed in (never imported from app — that would be a
circular import). Expiry policy lives here: 7-day user tokens, 5-minute
2FA pending tokens.
"""
import datetime

import jwt


def mint_user_token(user_id, email, secret, algo="HS256", days=7):
    return jwt.encode(
        {"user_id": user_id, "email": email,
         "exp": datetime.datetime.utcnow() + datetime.timedelta(days=days)},
        secret, algorithm=algo,
    )


def mint_temp_token(user_id, email, secret, algo="HS256", minutes=5):
    return jwt.encode(
        {"user_id": user_id, "email": email,
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes),
         "2fa_pending": True},
        secret, algorithm=algo,
    )


def decode(token, secret, algo="HS256"):
    """Return payload; raises jwt.ExpiredSignatureError / jwt.InvalidTokenError."""
    return jwt.decode(token, secret, algorithms=[algo])

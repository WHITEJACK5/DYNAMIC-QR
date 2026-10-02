"""Authentication: register/login, password reset, TOTP 2FA, /api/me."""

import datetime, hashlib, secrets

from app.config import JWT_ALGO, JWT_SECRET, logger
from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import get_base_url, get_session, rate_limit, token_required
from app.models import User as _User
from app.repositories import folders_repo, users_repo
from app.schemas import (
    Disable2FARequest, ForgotRequest, Login2FARequest, LoginRequest,
    LogoutRequest, RefreshRequest, RegisterRequest, ResendVerificationRequest,
    ResetRequest, TwoFACodeRequest, VerifyEmailRequest, first_error,
)
from app.services import mailer as _mailer
from app.services import tokens as _tokens
from app.services.render import create_qr_image, image_to_base64

import jwt

auth = Blueprint("auth", __name__)


@auth.route("/api/register", methods=["POST"])
@auth.route("/api/v1/register", methods=["POST"])
@rate_limit(limit=5, window=60, key_func=lambda: request.remote_addr or "unknown")
def register():
    try:
        req = RegisterRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    email, password, name = req.email, req.password, req.name
    s = get_session()
    try:
        if users_repo.find_id_by_email(s, email):
            s.close()
            return jsonify({"error":"Email already registered"}), 409
        pwd_hash = generate_password_hash(password)
        uid = users_repo.create_user(s, email, pwd_hash, name)
        folders_repo.create_for_user(s, uid, "My QR Codes")
        token, refresh = _tokens.mint_pair(uid, email, JWT_SECRET, JWT_ALGO)
        # Phase 4d: issue the confirmation link. Unverified accounts may use
        # static QRs but not dynamic ones.
        sent, _raw = _issue_verification(s, email, get_base_url(request))
        s.close()
        logger.info("New user registered: %s", email)
        if not sent:
            logger.warning(
                "Registration succeeded but the verification email was not "
                "delivered for %s; account is unverified until it is sent",
                email,
            )
        # "token" kept alongside the explicit names so existing clients and
        # the frontend keep working; it is the 15-minute access token.
        return jsonify({"token":token,"access_token":token,"refresh_token":refresh,
                        "expires_in":_tokens.ACCESS_MINUTES * 60,
                        "email_verified": False,
                        "verification_email_sent": sent,
                        "user":{"id":uid,"email":email,"name":name}})
    except Exception as e:
        logger.exception("Register error for %s: %s", email, e)
        try:
            s.close()
        except Exception:
            pass
        return jsonify({"error":"Registration failed"}), 500


@auth.route("/api/login", methods=["POST"])
@auth.route("/api/v1/login", methods=["POST"])
@rate_limit(limit=5, window=60, key_func=lambda: request.remote_addr or "unknown")
def login():
    try:
        req = LoginRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    email, password = req.email, req.password
    s = get_session()
    row = users_repo.find_by_email(s, email)
    s.close()
    if not row or not check_password_hash(row["password_hash"], password):
        logger.warning("Failed login attempt for %s from %s", email, request.remote_addr)
        return jsonify({"error":"Invalid credentials"}), 401
    # Check 2FA
    if row["twofa_enabled"]:
        # Don't issue token yet — require 2FA step
        temp_token = _tokens.mint_temp_token(row["id"], email, JWT_SECRET, JWT_ALGO)
        return jsonify({"need_2fa": True, "temp_token": temp_token, "message": "2FA required"})
    token, refresh = _tokens.mint_pair(row["id"], email, JWT_SECRET, JWT_ALGO)
    logger.info("User login: %s", email)
    return jsonify({"token":token,"access_token":token,"refresh_token":refresh,
                    "expires_in":_tokens.ACCESS_MINUTES * 60,
                    "user":{"id":row["id"],"email":email,"name":row["name"]}})


VERIFY_TOKEN_TTL_HOURS = 24


def _issue_verification(session, email, base_url):
    """Create a verification token, store its hash, and try to send the link.

    Returns (sent, plain_token). The raw token is returned so tests and the
    dev-only log path can use it; only its hash is persisted.
    """
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(hours=VERIFY_TOKEN_TTL_HOURS)).isoformat()
    users_repo.set_verify_token(session, email, token_hash, expires)
    url = _mailer.build_verify_url(base_url, raw)
    return _mailer.send_verification(email, url, VERIFY_TOKEN_TTL_HOURS), raw


@auth.route("/api/verify-email", methods=["GET", "POST"])
@auth.route("/api/v1/verify-email", methods=["GET", "POST"])
def verify_email():
    """Phase 4d: confirm an address.

    GET is required, not optional: the emailed link is a plain URL that a
    browser follows, so it arrives as a GET navigation. This route was
    POST-only, and because app/routes/pages.py serves the SPA for unmatched
    paths, a GET here quietly returned index.html with status 200 — so the
    link in every verification email did nothing, and a test that only
    asserted the status code passed against that HTML.
    """
    body = request.get_json(silent=True) or {}
    raw = body.get("token") or request.args.get("token")
    try:
        req = VerifyEmailRequest.model_validate({"token": raw})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    s = get_session()
    try:
        row = s.query(_User).filter(_User.verify_token == token_hash).one_or_none()
        if row is None:
            return jsonify({"error": "Invalid or already-used verification link"}), 400
        if row.verify_expires:
            try:
                if datetime.datetime.fromisoformat(row.verify_expires) < datetime.datetime.utcnow():
                    return jsonify({"error": "Verification link expired"}), 400
            except ValueError:
                return jsonify({"error": "Verification link invalid"}), 400
        email = row.email
        users_repo.mark_email_verified(s, email)
    finally:
        s.close()
    logger.info("Email verified: %s", email)
    return jsonify({"status": "verified", "email": email})


@auth.route("/api/resend-verification", methods=["POST"])
@auth.route("/api/v1/resend-verification", methods=["POST"])
@rate_limit(limit=5, window=60, key_func=lambda: request.remote_addr or "unknown")
def resend_verification():
    """Reissue a verification link.

    Every outcome returns the same 202 and the same body. Distinguishing
    "no such account", "already verified" and "mail not delivered" by
    status code would be an account-enumeration oracle, so delivery
    failures are logged instead of reported. A user checks their own state
    through GET /api/me, which requires their token.
    """
    neutral = {"status": "If that account needs verification, a link has been sent"}
    try:
        req = ResendVerificationRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    s = get_session()
    try:
        state = users_repo.find_verify(s, req.email)
        if state is None or state["email_verified"]:
            return jsonify(neutral), 202
        sent, _raw = _issue_verification(s, req.email, get_base_url(request))
    finally:
        s.close()
    if not sent:
        logger.error(
            "Verification email for %s was not delivered; the account stays "
            "unverified until SMTP is configured or the user retries", req.email
        )
    else:
        logger.info("Verification email re-sent to %s", req.email)
    return jsonify(neutral), 202


@auth.route("/api/refresh", methods=["POST"])
@auth.route("/api/v1/refresh", methods=["POST"])
@rate_limit(limit=30, window=60, key_func=lambda: request.remote_addr or "unknown")
def refresh_tokens():
    """Phase 4c: trade a refresh token for a new pair.

    The presented refresh token is revoked as the new one is issued
    (rotation), so a captured refresh token works at most once.
    """
    try:
        req = RefreshRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    try:
        data = _tokens.decode(req.refresh_token, JWT_SECRET, JWT_ALGO)
    except Exception as e:
        if e.__class__.__name__ == "ExpiredSignatureError":
            return jsonify({"error": "Refresh token expired"}), 401
        logger.warning("Invalid refresh token: %s", e)
        return jsonify({"error": "Invalid refresh token"}), 401
    # An access token must not work here: that would let a 15-minute token
    # mint itself a 30-day refresh token.
    if data.get("typ") != _tokens.REFRESH:
        return jsonify({"error": "Not a refresh token"}), 401
    if _tokens.is_revoked(data.get("jti")):
        logger.warning("Refresh token reuse detected (already rotated or revoked)")
        return jsonify({"error": "Refresh token revoked"}), 401

    _tokens.revoke(data)
    token, new_refresh = _tokens.mint_pair(data["user_id"], data["email"],
                                          JWT_SECRET, JWT_ALGO)
    return jsonify({"token":token,"access_token":token,"refresh_token":new_refresh,
                    "expires_in":_tokens.ACCESS_MINUTES * 60})


@auth.route("/api/logout", methods=["POST"])
@auth.route("/api/v1/logout", methods=["POST"])
def logout():
    """Phase 4c: revoke the presented access token (and refresh token).

    The access token is read directly rather than via @token_required so a
    revoked or expired one can still be logged out idempotently.
    """
    revoked = 0
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        try:
            data = _tokens.decode(header.split(" ", 1)[1], JWT_SECRET, JWT_ALGO)
            if data.get("typ") != _tokens.REFRESH and _tokens.revoke(data):
                revoked += 1
        except Exception:
            pass  # already invalid: nothing to revoke
    try:
        body = LogoutRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError:
        body = None
    if body and body.refresh_token:
        try:
            data = _tokens.decode(body.refresh_token, JWT_SECRET, JWT_ALGO)
            if data.get("typ") == _tokens.REFRESH and _tokens.revoke(data):
                revoked += 1
        except Exception:
            pass
    return jsonify({"status": "logged out", "revoked": revoked})


@auth.route("/api/forgot-password", methods=["POST"])
@auth.route("/api/v1/forgot-password", methods=["POST"])
@rate_limit(limit=3, window=600)
def forgot_password():
    try:
        req = ForgotRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    email = req.email
    s = get_session()
    if not users_repo.find_id_by_email(s, email):
        s.close()
        # Don't reveal if email exists
        return jsonify({"message":"If that email exists, a reset link has been generated. Check server logs (personal use)."}), 200
    # Generate reset token valid 15 min
    reset_token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).isoformat()
    users_repo.set_reset_token(s, email, generate_password_hash(reset_token), expires)
    s.close()
    # For personal use, log token (in real app, email it)
    logger.info("Password reset token for %s: %s (expires %s)", email, reset_token, expires)
    logger.info("[NARE & CO.] Password reset for %s: token=%s expires %s", email, reset_token, expires)
    # Return token directly for personal local use (so user can see it)
    return jsonify({"message":"Reset token generated (see server logs).","reset_token": reset_token, "expires": expires}), 200


@auth.route("/api/reset-password", methods=["POST"])
@auth.route("/api/v1/reset-password", methods=["POST"])
def reset_password():
    try:
        req = ResetRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    email, token, new_pwd = req.email, req.token, req.new_password
    s = get_session()
    row = users_repo.find_reset(s, email)
    if not row or not row["reset_token"]:
        s.close()
        return jsonify({"error":"Invalid or expired reset token"}), 400
    try:
        exp = datetime.datetime.fromisoformat(row["reset_expires"])
        if datetime.datetime.utcnow() > exp:
            s.close()
            return jsonify({"error":"Reset token expired"}), 400
    except Exception:
        pass
    if not check_password_hash(row["reset_token"], token):
        s.close()
        return jsonify({"error":"Invalid token"}), 400
    users_repo.complete_reset(s, email, generate_password_hash(new_pwd))
    s.close()
    logger.info("Password reset successful for %s", email)
    return jsonify({"message":"Password updated"}), 200

# 2FA endpoints


@auth.route("/api/2fa/setup", methods=["POST"])
@auth.route("/api/v1/2fa/setup", methods=["POST"])
@token_required
def setup_2fa():
    try:
        import pyotp
        s = get_session()
        row = users_repo.get_2fa(s, g.user_id)
        secret = row["twofa_secret"] if row and row["twofa_secret"] else pyotp.random_base32()
        if not row or not row["twofa_secret"]:
            users_repo.set_2fa_secret(s, g.user_id, secret)
        # Generate QR provisioning URI
        user_email = g.user_email
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user_email, issuer_name="NARE & CO.")
        # Also generate QR image for the URI
        qr_img = create_qr_image(uri, size=400)
        b64 = image_to_base64(qr_img)
        s.close()
        return jsonify({"secret": secret, "uri": uri, "qr_base64": f"data:image/png;base64,{b64}"})
    except ImportError:
        return jsonify({"error":"2FA not available (pyotp not installed)"}), 500
    except Exception as e:
        logger.exception("2FA setup failed: %s", e)
        return jsonify({"error":"2FA setup failed"}), 500


@auth.route("/api/2fa/verify-setup", methods=["POST"])
@auth.route("/api/v1/2fa/verify-setup", methods=["POST"])
@token_required
def verify_2fa_setup():
    try:
        req = TwoFACodeRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    code = req.code
    try:
        import pyotp
        s = get_session()
        row = users_repo.get_2fa(s, g.user_id)
        if not row or not row["twofa_secret"]:
            s.close()
            return jsonify({"error":"No secret, call /setup first"}), 400
        totp = pyotp.TOTP(row["twofa_secret"])
        if totp.verify(code, valid_window=1):
            users_repo.set_2fa_enabled(s, g.user_id, True)
            s.close()
            logger.info("2FA enabled for user %s", g.user_id)
            return jsonify({"message":"2FA enabled"})
        s.close()
        return jsonify({"error":"Invalid code"}), 400
    except Exception as e:
        logger.exception("2FA verify failed: %s", e)
        return jsonify({"error":"Verify failed"}), 500


@auth.route("/api/2fa/disable", methods=["POST"])
@auth.route("/api/v1/2fa/disable", methods=["POST"])
@token_required
def disable_2fa():
    code = Disable2FARequest.model_validate(request.get_json(silent=True) or {}).code
    # If 2FA enabled, require code to disable
    s = get_session()
    row = users_repo.get_2fa(s, g.user_id)
    if row and row["twofa_enabled"]:
        if not code:
            s.close()
            return jsonify({"error":"code required to disable"}), 400
        try:
            import pyotp
            totp = pyotp.TOTP(row["twofa_secret"])
            if not totp.verify(code, valid_window=1):
                s.close()
                return jsonify({"error":"Invalid code"}), 400
        except Exception as e:
            logger.warning("2FA disable verify failed: %s", e)
            s.close()
            return jsonify({"error":"Invalid code"}), 400
    users_repo.clear_2fa(s, g.user_id)
    s.close()
    return jsonify({"message":"2FA disabled"})


@auth.route("/api/2fa/login-verify", methods=["POST"])
@auth.route("/api/v1/2fa/login-verify", methods=["POST"])
def login_2fa_verify():
    try:
        req = Login2FARequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    temp_token, code = req.temp_token, req.code
    try:
        payload = _tokens.decode(temp_token, JWT_SECRET, JWT_ALGO)
        if not payload.get("2fa_pending"):
            return jsonify({"error":"Invalid temp token"}), 400
        uid = payload["user_id"]
        email = payload["email"]
        s = get_session()
        row = users_repo.get_2fa(s, uid)
        s.close()
        if not row or not row["twofa_secret"]:
            return jsonify({"error":"2FA not set up"}), 400
        import pyotp
        totp = pyotp.TOTP(row["twofa_secret"])
        if totp.verify(code, valid_window=1):
            token, refresh = _tokens.mint_pair(uid, email, JWT_SECRET, JWT_ALGO)
            return jsonify({"token": token, "access_token": token,
                            "refresh_token": refresh,
                            "expires_in": _tokens.ACCESS_MINUTES * 60,
                            "user": {"id": uid, "email": email}})
        return jsonify({"error":"Invalid 2FA code"}), 401
    except jwt.ExpiredSignatureError:
        return jsonify({"error":"Temp token expired"}), 401
    except Exception as e:
        logger.warning("2FA login verify failed: %s", e)
        return jsonify({"error":"Verify failed"}), 401


@auth.route("/api/me", methods=["GET"])
@auth.route("/api/v1/me", methods=["GET"])
@token_required
def me():
    s = get_session()
    user = users_repo.find_public_by_id(s, g.user_id)
    s.close()
    if not user:
        return jsonify({"error":"User not found"}), 404
    return jsonify(user)

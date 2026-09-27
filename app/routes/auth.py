"""Authentication: register/login, password reset, TOTP 2FA, /api/me."""

import datetime, secrets

from app.config import JWT_ALGO, JWT_SECRET, logger
from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import get_session, rate_limit, token_required
from app.repositories import folders_repo, users_repo
from app.schemas import (
    Disable2FARequest, ForgotRequest, Login2FARequest, LoginRequest,
    RegisterRequest, ResetRequest, TwoFACodeRequest, first_error,
)
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
        token = _tokens.mint_user_token(uid, email, JWT_SECRET, JWT_ALGO)
        s.close()
        logger.info(f"New user registered: {email}")
        return jsonify({"token":token,"user":{"id":uid,"email":email,"name":name}})
    except Exception as e:
        logger.exception(f"Register error for {email}: {e}")
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
        logger.warning(f"Failed login attempt for {email} from {request.remote_addr}")
        return jsonify({"error":"Invalid credentials"}), 401
    # Check 2FA
    if row["twofa_enabled"]:
        # Don't issue token yet — require 2FA step
        temp_token = _tokens.mint_temp_token(row["id"], email, JWT_SECRET, JWT_ALGO)
        return jsonify({"need_2fa": True, "temp_token": temp_token, "message": "2FA required"})
    token = _tokens.mint_user_token(row["id"], email, JWT_SECRET, JWT_ALGO)
    logger.info(f"User login: {email}")
    return jsonify({"token":token,"user":{"id":row["id"],"email":email,"name":row["name"]}})


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
    logger.info(f"Password reset token for {email}: {reset_token} (expires {expires})")
    print(f"[NARE & CO.] Password reset for {email}: token={reset_token} expires {expires}")
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
    logger.info(f"Password reset successful for {email}")
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
        logger.exception(f"2FA setup failed: {e}")
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
            logger.info(f"2FA enabled for user {g.user_id}")
            return jsonify({"message":"2FA enabled"})
        s.close()
        return jsonify({"error":"Invalid code"}), 400
    except Exception as e:
        logger.exception(f"2FA verify failed: {e}")
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
            logger.warning(f"2FA disable verify failed: {e}")
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
            token = _tokens.mint_user_token(uid, email, JWT_SECRET, JWT_ALGO)
            return jsonify({"token": token, "user": {"id": uid, "email": email}})
        return jsonify({"error":"Invalid 2FA code"}), 401
    except jwt.ExpiredSignatureError:
        return jsonify({"error":"Temp token expired"}), 401
    except Exception as e:
        logger.warning(f"2FA login verify failed: {e}")
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

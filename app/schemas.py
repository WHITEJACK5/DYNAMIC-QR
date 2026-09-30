"""Explicit request schemas (Phase 2c auth, Phase 2i update/folders/templates).

Pydantic v2 is the single source of truth for shape + normalization +
domain rules. Validators reuse core.utils so messages stay identical to
the pre-schema handlers. Auth models use "" defaults (absent keys never
raise bare "Field required"); partial-update models use None defaults so
missing keys are skipped while explicit nulls keep their legacy meaning.
"""
import json
import re
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.utils import validate_email_format, validate_password_strength

HEX_COLOR = re.compile(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


def first_error(exc: ValidationError) -> str:
    """Return the original validator message (strip Pydantic's prefix)."""
    try:
        msg = exc.errors(include_url=False)[0].get("msg", "Invalid request")
    except Exception:
        return "Invalid request"
    if ", " in msg and msg.split(", ", 1)[0].endswith("error"):
        return msg.split(", ", 1)[1]
    return msg


def _norm_email(v) -> str:
    return v.strip().lower() if isinstance(v, str) else ""


class RegisterRequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    email: str = ""
    password: str = ""
    name: str = ""

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        e = _norm_email(v)
        if not e:
            raise ValueError("Email and password required")
        if not validate_email_format(e):
            raise ValueError("Invalid email format")
        return e

    @field_validator("password", mode="before")
    @classmethod
    def _password(cls, v):
        p = v if isinstance(v, str) else ""
        if not p:
            raise ValueError("Email and password required")
        ok, msg = validate_password_strength(p)
        if not ok:
            raise ValueError(msg)
        return p

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v):
        return v if isinstance(v, str) else ""


class LoginRequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    email: str = ""
    password: str = ""

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        e = _norm_email(v)
        if not e:
            raise ValueError("Email and password required")
        return e

    @field_validator("password", mode="before")
    @classmethod
    def _password(cls, v):
        p = v if isinstance(v, str) else ""
        if not p:
            raise ValueError("Email and password required")
        return p


class QRUpdateRequest(BaseModel):
    """Partial update: only provided keys validate; messages match legacy."""

    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    type: Optional[str] = None
    content: Optional[str] = None
    data_json: Optional[Any] = None
    fg_color: Optional[str] = None
    bg_color: Optional[str] = None
    frame_color: Optional[str] = None
    gradient: Optional[str] = None
    pattern: Optional[str] = None
    eye_style: Optional[str] = None
    frame_text: Optional[str] = None
    folder_id: Optional[Any] = None
    password: Optional[Any] = None
    expiry_date: Optional[Any] = None
    scan_limit: Optional[Any] = None
    data: Optional[Any] = None

    @field_validator("fg_color", "bg_color", "frame_color", mode="before")
    @classmethod
    def _color(cls, v, info):
        if v is None or v == "":
            return v
        if not isinstance(v, str) or not HEX_COLOR.match(v):
            raise ValueError(f"Invalid color {info.field_name}")
        return v

    @field_validator("password", mode="before")
    @classmethod
    def _qr_password(cls, v):
        if v is None or v == "":
            return v  # clear-password path stays in the handler
        if not isinstance(v, str) or len(v) < 4:
            raise ValueError("Password too short")
        return v

    @field_validator("scan_limit", mode="before")
    @classmethod
    def _scan_limit(cls, v):
        if v is None:
            return v  # clear-limit path stays in the handler
        try:
            sl = int(v)
        except (TypeError, ValueError):
            raise ValueError("Invalid scan_limit")
        if sl <= 0:
            raise ValueError("Invalid scan_limit")
        return sl


class FolderCreateRequest(BaseModel):
    name: str = "New Folder"

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v):
        v = v if isinstance(v, str) else ""
        if not v or len(v) > 60:
            raise ValueError("Invalid folder name")
        return v


class TemplateCreateRequest(BaseModel):
    name: str = "Template"
    config: Any = {}

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v):
        return v if isinstance(v, str) else ""

    @field_validator("config", mode="before")
    @classmethod
    def _config(cls, v):
        if len(json.dumps(v if v is not None else {})) > 10000:
            raise ValueError("Config too large")
        return v


def _norm_qr_type(v) -> str:
    if v is None or v == "":
        return "url"
    if not isinstance(v, str):
        raise ValueError("Invalid type")
    return v


def _norm_qr_data(v) -> Any:
    if v is None or v == "":
        return {}
    if isinstance(v, str):
        return {"content": v}
    return v


def _check_color(v, field_name: str) -> str:
    if not isinstance(v, str) or not HEX_COLOR.match(v):
        raise ValueError(f"Invalid color {field_name}")
    return v


def _form_str(v, default: str = "") -> str:
    """Form values arrive as strings; an absent field means its default."""
    if v is None:
        return default
    if isinstance(v, str):
        return v if v != "" else default
    return str(v)


class QRStyle(BaseModel):
    """Shared style rules for generate/preview (colors strict like PUT)."""

    model_config = ConfigDict(extra="ignore")

    fg_color: str = "#0A0A0A"
    bg_color: str = "#FFFFFF"
    frame_color: str = "#00FF88"
    pattern: str = "square"
    eye_style: str = "square"
    gradient: str = "solid"
    frame_text: str = ""

    @field_validator("fg_color", mode="before")
    @classmethod
    def _fg(cls, v):
        return _check_color(v, "fg_color")

    @field_validator("bg_color", mode="before")
    @classmethod
    def _bg(cls, v):
        return _check_color(v, "bg_color")

    @field_validator("frame_color", mode="before")
    @classmethod
    def _fc(cls, v):
        return _check_color(v, "frame_color")

    @field_validator("pattern", "eye_style", "gradient", "frame_text", mode="before")
    @classmethod
    def _style_str(cls, v):
        return v if isinstance(v, str) else ""


class GenerateRequest(QRStyle):
    type: str = "url"
    data: Any = {}
    is_dynamic: bool = False
    name: Any = "My QR"
    logo_base64: Optional[str] = None
    # Access-control options (were read straight off the raw body before)
    password: Optional[Any] = None
    scan_limit: Optional[Any] = None
    expiry_date: Optional[Any] = None

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        return _norm_qr_type(v)

    @field_validator("scan_limit", mode="before")
    @classmethod
    def _scan_limit(cls, v):
        """Reject a scan_limit that cannot mean what the caller intended.

        This used to coerce junk to None, i.e. "no limit". A merchant who
        types 100, flicks a comma or a stray character, and gets a QR with no
        limit at all is the opposite of what a limit is for, and the failure
        is invisible — the QR keeps working forever. The old comment called
        it "never a 500", which was protecting against an exception that Pydantic
        raises cleanly as a 400 anyway.

        Both the JSON and multipart paths use this, so neither can be the
        looser one. Behaviour change for the JSON API is deliberate: a client
        sending scan_limit="abc" now gets 400 where it previously got a
        silently unlimited QR.
        """
        if v is None or v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("scan_limit must be a whole number")
        if n <= 0:
            raise ValueError("scan_limit must be greater than zero")
        if n > 1_000_000:
            raise ValueError("scan_limit is unreasonably large")
        return n

    @field_validator("data", mode="before")
    @classmethod
    def _data(cls, v):
        return _norm_qr_data(v)


class PreviewRequest(QRStyle):
    content: Optional[str] = None
    type: str = "url"
    data: Any = {}
    logo_base64: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        return _norm_qr_type(v)

    @field_validator("data", mode="before")
    @classmethod
    def _data(cls, v):
        return _norm_qr_data(v)


class GenerateFormRequest(BaseModel):
    """Input schema for the multipart branch of /api/generate (Phase 2b).

    The multipart path previously read request.form directly and applied no
    validation at all, so it accepted input the JSON path rejects: a form with
    fg_color="not-a-colour" returned 200 while the same value over JSON
    returned 400. One endpoint, two different contracts, and the looser one
    was the one a browser hits.

    Form values arrive as strings, so this coerces the same way a browser
    sends them while reusing QRStyle's colour rules rather than duplicating
    them. Unknown fields are ignored, matching the JSON schema.
    """

    model_config = ConfigDict(extra="ignore")

    type: str = "url"
    data: str = "{}"
    is_dynamic: bool = False
    fg_color: str = "#0A0A0A"
    bg_color: str = "#FFFFFF"
    frame_color: str = "#00FF88"
    pattern: str = "square"
    eye_style: str = "square"
    gradient: str = "solid"
    frame_text: str = ""
    name: str | None = None
    password: str | None = None
    scan_limit: int | None = None
    expiry_date: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        # an empty form field means "not supplied", not "empty string"
        return _form_str(v, "url")

    @field_validator("data", mode="before")
    @classmethod
    def _data(cls, v):
        return _form_str(v, "{}")

    @field_validator("fg_color", mode="before")
    @classmethod
    def _fg(cls, v):
        return _check_color(_form_str(v, "#0A0A0A"), "fg_color")

    @field_validator("bg_color", mode="before")
    @classmethod
    def _bg(cls, v):
        return _check_color(_form_str(v, "#FFFFFF"), "bg_color")

    @field_validator("frame_color", mode="before")
    @classmethod
    def _fc(cls, v):
        return _check_color(_form_str(v, "#00FF88"), "frame_color")

    @field_validator("is_dynamic", mode="before")
    @classmethod
    def _dyn(cls, v):
        # a browser sends the literal string "true"/"false"
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @field_validator("scan_limit", mode="before")
    @classmethod
    def _limit(cls, v):
        """Same rule as GenerateRequest, deliberately.

        A mangled scan_limit must not silently become an unlimited QR, so both
        paths reject it rather than coercing. Sharing one rule is the point:
        one endpoint cannot have a looser contract than its other.
        """
        if v is None or v == "":
            return None
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError("scan_limit must be a whole number")
        if n <= 0:
            raise ValueError("scan_limit must be greater than zero")
        if n > 1_000_000:
            raise ValueError("scan_limit is unreasonably large")
        return n


class BulkFormRequest(BaseModel):
    """Validation for the multipart bulk-upload form (the last route without a
    schema). The CSV file itself is streamed, not parsed here."""

    model_config = ConfigDict(extra="ignore")

    type: str = "url"
    fg_color: str = "#0A0A0A"
    bg_color: str = "#FFFFFF"

    @field_validator("type", mode="before")
    @classmethod
    def _type(cls, v):
        return _norm_qr_type(v)

    @field_validator("fg_color", "bg_color", mode="before")
    @classmethod
    def _color(cls, v, info):
        if not isinstance(v, str) or not HEX_COLOR.match(v):
            raise ValueError(f"Invalid color {info.field_name}")
        return v


class RefreshRequest(BaseModel):
    """Phase 4c: exchange a refresh token for a new access/refresh pair."""

    model_config = ConfigDict(validate_default=True)

    refresh_token: str = ""

    @field_validator("refresh_token", mode="before")
    @classmethod
    def _token(cls, v):
        t = (v or "").strip() if isinstance(v, str) else ""
        if not t:
            raise ValueError("refresh_token required")
        return t


class LogoutRequest(BaseModel):
    """Phase 4c: revoke an access token, and a refresh token if supplied."""

    model_config = ConfigDict(validate_default=True)

    refresh_token: str = ""

    @field_validator("refresh_token", mode="before")
    @classmethod
    def _token(cls, v):
        return (v or "").strip() if isinstance(v, str) else ""


class VerifyEmailRequest(BaseModel):
    """Phase 4d: confirm an address with the token from the email link."""

    model_config = ConfigDict(validate_default=True)

    token: str = ""

    @field_validator("token", mode="before")
    @classmethod
    def _token(cls, v):
        t = (v or "").strip() if isinstance(v, str) else ""
        if not t:
            raise ValueError("token required")
        return t


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    email: str = ""

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        e = _norm_email(v)
        if not e or not validate_email_format(e):
            raise ValueError("Valid email required")
        return e


class ForgotRequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    email: str = ""

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        e = _norm_email(v)
        if not e or not validate_email_format(e):
            raise ValueError("Valid email required")
        return e


class ResetRequest(BaseModel):
    model_config = ConfigDict(validate_default=True, populate_by_name=True)

    email: str = ""
    token: str = ""
    new_password: str = Field(default="", validation_alias=AliasChoices("new_password", "password"))

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, v):
        e = _norm_email(v)
        if not e:
            raise ValueError("email, token and new_password required")
        return e

    @field_validator("token", mode="before")
    @classmethod
    def _token(cls, v):
        t = v if isinstance(v, str) else ""
        if not t:
            raise ValueError("email, token and new_password required")
        return t

    @field_validator("new_password", mode="before")
    @classmethod
    def _pwd(cls, v):
        p = v if isinstance(v, str) else ""
        if not p:
            raise ValueError("email, token and new_password required")
        ok, msg = validate_password_strength(p)
        if not ok:
            raise ValueError(msg)
        return p


class TwoFACodeRequest(BaseModel):
    """Strict code (verify-setup). Empty -> 'code required'."""

    model_config = ConfigDict(validate_default=True)

    code: str = ""

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, v):
        c = v.strip() if isinstance(v, str) else ""
        if not c:
            raise ValueError("code required")
        return c


class Disable2FARequest(BaseModel):
    """Lenient normalize only; the required-check stays in the handler
    because code is mandatory solely when 2FA is currently enabled."""

    code: str = ""

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, v):
        return v.strip() if isinstance(v, str) else ""


class Login2FARequest(BaseModel):
    model_config = ConfigDict(validate_default=True)

    temp_token: str = ""
    code: str = ""

    @field_validator("temp_token", mode="before")
    @classmethod
    def _tok(cls, v):
        t = v if isinstance(v, str) else ""
        if not t:
            raise ValueError("temp_token and code required")
        return t

    @field_validator("code", mode="before")
    @classmethod
    def _code(cls, v):
        c = v.strip() if isinstance(v, str) else ""
        if not c:
            raise ValueError("temp_token and code required")
        return c

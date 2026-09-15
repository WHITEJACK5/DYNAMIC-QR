"""Explicit request schemas, Phase 2c first slice (auth only).

Pydantic v2 is the single source of truth for shape + normalization +
domain rules. Validators reuse core.utils so messages stay identical to
the pre-schema handlers (tests assert on "at least 8", "Invalid email").
Missing/empty email+password map to "Email and password required" via
"" defaults (absent keys never raise bare "Field required").
"""
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from core.utils import validate_email_format, validate_password_strength


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

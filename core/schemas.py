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

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from core.utils import validate_email_format, validate_password_strength

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

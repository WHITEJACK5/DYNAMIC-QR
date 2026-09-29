"""Output (response) schemas for the HTTP API (Phase 2b, output half).

The directive requires that "every endpoint gets an explicit input schema
and a documented output schema". The input half lives in app/schemas.py as
Pydantic request models; this is the half that was missing, and it is
declared as real models rather than prose so it can be tested.

These models document the contract. They are not enforced at runtime by
serialising responses through them — the handlers return jsonify(dict) for
performance and because several responses are assembled from repository
dicts. What IS enforced is that the contract matches reality:
tests/test_api_contract.py asserts every model here validates against a real
response captured from the running app, and that every route is listed.
A model that drifts from the code fails the build.

Naming: `*Out` for a resource, `*Envelope` for a collection, `ErrorOut` for
the error shape. Optional fields use | None because the underlying columns
are nullable.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    # Every repository dict is already plain JSON types; allow the loose
    # values that reach responses (e.g. a legacy int stored in a bool column)
    # without pretending they are something they are not.
    model_config = ConfigDict(extra="allow")


class ErrorOut(_Out):
    error: str


class UserOut(_Out):
    id: int
    email: str
    name: str | None = None
    created_at: str | None = None
    is_premium: int | None = None
    twofa_enabled: int | None = None
    email_verified: bool | None = None


class SessionOut(_Out):
    """register / login / refresh response."""

    token: str
    access_token: str
    refresh_token: str
    expires_in: int
    user: dict[str, Any] | None = None
    email_verified: bool | None = None
    verification_email_sent: bool | None = None


class TwoFARequiredOut(_Out):
    need_2fa: bool
    temp_token: str
    message: str


class QRCodeOut(_Out):
    """A QR code as the API returns it.

    password_hash is deliberately absent: qr_repo.to_public() strips it, and
    this model is the documented version of that. has_logo replaces
    logo_path so an absolute server path never reaches a client.
    """

    id: int
    user_id: int | None = None
    folder_id: int | None = None
    name: str | None = None
    type: str | None = None
    content: str | None = None
    data_json: str | None = None
    is_dynamic: int | None = None
    short_code: str | None = None
    fg_color: str | None = None
    bg_color: str | None = None
    gradient: str | None = None
    pattern: str | None = None
    eye_style: str | None = None
    frame_text: str | None = None
    frame_color: str | None = None
    logo_path: str | None = None
    has_logo: bool | None = None
    has_password: int | None = None
    password_hash: None = None  # must never be present
    expiry_date: str | None = None
    scan_limit: int | None = None
    scan_count: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ScanOut(_Out):
    id: int
    qr_id: int | None = None
    timestamp: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    device: str | None = None
    browser: str | None = None
    os: str | None = None
    country: str | None = None
    city: str | None = None


class CountBucket(_Out):
    """A grouped count, e.g. {"device": "Mobile", "c": 12}."""

    c: int
    country: str | None = None
    device: str | None = None


class TimelineBucket(_Out):
    c: int
    d: str


class QRCodeListEnvelope(_Out):
    """Paginated collection: items + total + the window that was served."""

    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class FolderOut(_Out):
    id: int
    user_id: int | None = None
    name: str | None = None
    created_at: str | None = None


class TemplateOut(_Out):
    id: int
    user_id: int | None = None
    name: str | None = None
    config_json: str | None = None
    created_at: str | None = None


class GenerateOut(_Out):
    """POST /api/generate."""

    content: str
    image_base64: str
    is_dynamic: bool | None = None
    qr_id: int | None = None
    short_code: str | None = None
    id: int | None = None
    original_content: str | None = None


class PreviewOut(_Out):
    image_base64: str
    content: str | None = None


class QRAnalyticsOut(_Out):
    """GET /api/qrcodes/<id>/analytics."""

    qr: dict[str, Any]
    scans: list[dict[str, Any]]
    total_scans: int | None = None
    devices: list[dict[str, Any]] = Field(default_factory=list)
    countries: list[dict[str, Any]] = Field(default_factory=list)
    # Phase 5 audit: the scan list is paginated, so the envelope has to say
    # how many exist and how many were served.
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class AnalyticsOverviewOut(_Out):
    total_qrs: int | None = None
    total_scans: int | None = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    devices: list[dict[str, Any]] = Field(default_factory=list)
    countries: list[dict[str, Any]] = Field(default_factory=list)
    top: list[dict[str, Any]] = Field(default_factory=list)


class HealthOut(_Out):
    status: str
    version: str | None = None
    database: str | None = None


class MessageOut(_Out):
    """A plain acknowledgement, e.g. logout, resend, password reset."""

    status: str | None = None
    message: str | None = None
    revoked: int | None = None


class VerifyEmailOut(_Out):
    status: str
    email: str


class JobOut(_Out):
    job_id: str
    status: str | None = None
    count: int | None = None
    result: Any = None


class DeprecationHeaders(_Out):
    """Not a body: the headers a legacy /api/* response carries."""

    Deprecation: str = "true"
    Link: str | None = None

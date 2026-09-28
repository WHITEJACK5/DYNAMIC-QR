"""Pure helper functions (Phase 2a).

The directive lists `app/utils/` as a required layer, so this is a package
split by concern:

    validation.py  colour parsing, short codes, email/password checks
    qr_content.py  QR payload construction per type
    device.py      user-agent parsing

Everything is re-exported here, so the existing
`from app.utils import build_qr_content, generate_short_code, ...` call sites
in routes, services, repositories and server.py are unchanged.

No Flask, no DB, no network: everything here is unit-testable in isolation.
"""
from app.utils.device import detect_device
from app.utils.qr_content import build_gs1_content, build_qr_content
from app.utils.validation import (
    generate_short_code,
    hex_to_rgb,
    validate_email_format,
    validate_password_strength,
)

__all__ = [
    "detect_device",
    "build_gs1_content",
    "build_qr_content",
    "generate_short_code",
    "hex_to_rgb",
    "validate_email_format",
    "validate_password_strength",
]

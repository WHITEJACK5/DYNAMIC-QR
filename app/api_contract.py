"""The API contract: which output schema each endpoint returns (Phase 2b).

A list of output models in a module is documentation; a registry that is
checked against the live route table is a contract. This maps every public
endpoint to its documented response, so an endpoint added without one is a
failing test rather than an undocumented surprise.

Tests assert:
  * every rule the app actually registers appears here
  * every entry here points at a real, constructible model
  * the models validate against responses captured from the running app
"""
from app import schemas_out as out

#: endpoint -> (success status, output model, notes)
#:
#: Keys are the *newest* path, without the /api or /api/v1 prefix, because
#: both are served. The error shape is `out.ErrorOut` everywhere and is not
#: repeated per entry.
CONTRACT: dict[str, tuple[int, type]] = {
    # --- auth -----------------------------------------------------------
    "register": (200, out.SessionOut),
    "login": (200, out.SessionOut),
    # login answers 200 with a 2FA challenge before any token exists
    "2fa/login-verify": (200, out.SessionOut),
    "refresh": (200, out.SessionOut),
    "logout": (200, out.MessageOut),
    "me": (200, out.UserOut),
    "2fa/setup": (200, dict),          # returns the provisioning payload
    "2fa/verify-setup": (200, out.MessageOut),
    "2fa/disable": (200, out.MessageOut),
    "forgot-password": (200, out.MessageOut),
    "reset-password": (200, out.MessageOut),
    "verify-email": (200, out.VerifyEmailOut),
    "resend-verification": (202, out.MessageOut),

    # --- QR codes -------------------------------------------------------
    "generate": (200, out.GenerateOut),
    "preview": (200, out.PreviewOut),
    "qrcodes": (200, out.QRCodeListEnvelope),
    "qrcodes/<int:qr_id>": (200, out.QRCodeOut),
    "qrcodes/<int:qr_id>/duplicate": (200, out.MessageOut),
    "qrcodes/<int:qr_id>/analytics": (200, out.QRAnalyticsOut),
    "qrcodes/bulk": (200, out.JobOut),
    "qrcodes/bulk/<job_id>": (200, out.JobOut),
    "download/<int:qr_id>": (200, dict),   # an image, not JSON

    # --- metadata -------------------------------------------------------
    "folders": (200, out.FolderOut),
    "templates": (200, out.TemplateOut),

    # --- ops ------------------------------------------------------------
    "health": (200, out.HealthOut),
    "analytics/overview": (200, out.AnalyticsOverviewOut),
    # Phase 7d: Prometheus text, not JSON — same escape hatch as download
    "metrics": (200, dict),
    # Phase 9: generated docs. Swagger UI is HTML; the spec is JSON.
    "docs": (200, dict),
    "openapi.json": (200, dict),
}

#: Endpoints that return a non-JSON body.
BINARY_ENDPOINTS = {"download/<int:qr_id>"}

#: Endpoints whose collection form is the legacy bare list when no
#: pagination parameters are supplied. Documented because it is a real
#: inconsistency a client has to handle, not something to hide.
LEGACY_BARE_LIST = {"qrcodes", "folders", "templates"}


def documented(path: str) -> tuple[int, type] | None:
    return CONTRACT.get(path)


def normalise(rule: str) -> str:
    """Strip the version prefix and leading slash from a Flask rule.

    /api/v1/qrcodes -> qrcodes
    /api/qrcodes    -> qrcodes
    /metrics        -> metrics      (no /api prefix: it is not JSON)
    /r/<code>       -> r/<code>
    """
    for prefix in ("/api/v1", "/api"):
        if rule.startswith(prefix + "/"):
            return rule[len(prefix) + 1:]
    return rule.lstrip("/")

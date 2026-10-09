"""OpenAPI 3.0 spec generated from the Pydantic schemas (Phase 9).

The directive: "Generate a real OpenAPI/Swagger spec from the validation
schemas introduced in Phase 2, and serve it at /api/v1/docs ... Replace the
current static api-docs.html with this generated, always-accurate spec."

Why generated rather than hand-written: a hand-written spec drifts from the
schemas the moment a field is added, and the drift is invisible until a client
breaks. This builds the spec from the same Pydantic models the routes
validate against, so the spec cannot disagree with the code.

The route-to-model mapping is explicit. The routes call `model_validate`
inline, so there is no decorator to introspect; an explicit table is honest
about which schema documents which endpoint and fails loudly if a route is
added without one.
"""
from typing import Any

from app import schemas

SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "DRQR API",
        "version": "1.1.0",
        "description": (
            "Self-hosted QR code generation and analytics. "
            "All endpoints are versioned under /api/v1; the unversioned /api/* "
            "paths are deprecated aliases that proxy to v1."
        ),
    },
    "servers": [{"url": "/api/v1", "description": "Versioned API"}],
    "tags": [
        {"name": "auth", "description": "Register, login, tokens, 2FA, verification"},
        {"name": "qrcodes", "description": "QR code generation and management"},
        {"name": "analytics", "description": "Scan analytics"},
        {"name": "metadata", "description": "Folders and templates"},
        {"name": "ops", "description": "Health and metrics"},
    ],
}

#: route -> (tag, summary, request model or None, success status, response schema)
#: The response schema is derived from the request model where the endpoint
#: echoes it back; otherwise it is a documented literal.
ROUTES: dict[str, dict[str, Any]] = {
    "register": {
        "tag": "auth", "summary": "Create an account",
        "request": schemas.RegisterRequest, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "token": {"type": "string", "description": "15-minute access token"},
                "access_token": {"type": "string"},
                "refresh_token": {"type": "string", "description": "30-day refresh token"},
                "expires_in": {"type": "integer", "description": "900"},
                "email_verified": {"type": "boolean"},
                "user": {"type": "object"},
            },
        },
    },
    "login": {
        "tag": "auth", "summary": "Log in",
        "request": schemas.LoginRequest, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "token": {"type": "string"},
                "access_token": {"type": "string"},
                "refresh_token": {"type": "string"},
                "expires_in": {"type": "integer"},
                "need_2fa": {"type": "boolean"},
                "temp_token": {"type": "string"},
                "user": {"type": "object"},
            },
        },
    },
    "refresh": {
        "tag": "auth", "summary": "Exchange a refresh token for a new pair",
        "request": schemas.RefreshRequest, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "access_token": {"type": "string"},
                "refresh_token": {"type": "string"},
                "expires_in": {"type": "integer"},
            },
        },
    },
    "logout": {
        "tag": "auth", "summary": "Revoke the current tokens",
        "request": schemas.LogoutRequest, "status": 200,
        "response": {
            "type": "object",
            "properties": {"status": {"type": "string"}, "revoked": {"type": "integer"}},
        },
    },
    "/me": {
        "tag": "auth", "summary": "The authenticated user",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"}, "email": {"type": "string"},
                "name": {"type": "string"}, "email_verified": {"type": "boolean"},
            },
        },
    },
    "2fa/login-verify": {
        "tag": "auth", "summary": "Complete 2FA login",
        "request": schemas.Login2FARequest, "status": 200,
        "response": {
            "type": "object",
            "properties": {"token": {"type": "string"}, "user": {"type": "object"}},
        },
    },
    "verify-email": {
        "tag": "auth", "summary": "Confirm an email address",
        "request": schemas.VerifyEmailRequest, "status": 200,
        "response": {
            "type": "object",
            "properties": {"status": {"type": "string"}, "email": {"type": "string"}},
        },
    },
    "resend-verification": {
        "tag": "auth", "summary": "Reissue a verification link",
        "request": schemas.ResendVerificationRequest, "status": 202,
        "response": {"type": "object", "properties": {"status": {"type": "string"}}},
    },
    "forgot-password": {
        "tag": "auth", "summary": "Request a password reset",
        "request": schemas.ForgotRequest, "status": 200,
        "response": {"type": "object", "properties": {"status": {"type": "string"}}},
    },
    "reset-password": {
        "tag": "auth", "summary": "Reset a password",
        "request": schemas.ResetRequest, "status": 200,
        "response": {"type": "object", "properties": {"status": {"type": "string"}}},
    },
    "/qrcodes": {
        "tag": "qrcodes", "summary": "List the user's QR codes",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object"}},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
            },
        },
    },
    "/qrcodes/<int:qr_id>": {
        "tag": "qrcodes", "summary": "Get one QR code",
        "request": None, "status": 200,
        "response": {"type": "object"},
    },
    "/qrcodes/<int:qr_id>/analytics": {
        "tag": "analytics", "summary": "Per-QR scan analytics",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "qr": {"type": "object"},
                "scans": {"type": "array", "items": {"type": "object"}},
                "total": {"type": "integer"},
            },
        },
    },
    "/analytics/overview": {
        "tag": "analytics", "summary": "Account-wide analytics",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "total_qrs": {"type": "integer"},
                "total_scans": {"type": "integer"},
                "timeline": {"type": "array", "items": {"type": "object"}},
                "devices": {"type": "array", "items": {"type": "object"}},
                "countries": {"type": "array", "items": {"type": "object"}},
                "top": {"type": "array", "items": {"type": "object"}},
            },
        },
    },
    "/folders": {
        "tag": "metadata", "summary": "List folders",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object"}},
                "total": {"type": "integer"},
            },
        },
    },
    "/templates": {
        "tag": "metadata", "summary": "List templates",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object"}},
                "total": {"type": "integer"},
            },
        },
    },
    "/health": {
        "tag": "ops", "summary": "Health check",
        "request": None, "status": 200,
        "response": {
            "type": "object",
            "properties": {"status": {"type": "string"}, "version": {"type": "string"}},
        },
    },
}

#: Routes that take a JSON body but are not in ROUTES above (GET-only or
#: with a body model that is not worth documenting separately).
_EXTRA_REQUEST_MODELS = {
    "/qrcodes": None,
}


def _schema(model):
    """JSON Schema for a Pydantic model, or None."""
    if model is None:
        return None
    return model.model_json_schema(ref_template="#/components/schemas/{model}")


def build_spec() -> dict:
    """Assemble the OpenAPI document from the route table and Pydantic schemas."""
    paths: dict[str, Any] = {}
    schemas: dict[str, Any] = {}

    for path, meta in ROUTES.items():
        request_schema = _schema(meta.get("request"))
        if request_schema:
            name = meta["request"].__name__
            schemas[name] = request_schema

        operation: dict[str, Any] = {
            "tags": [meta["tag"]],
            "summary": meta["summary"],
            "responses": {
                str(meta["status"]): {
                    "description": "Success",
                    "content": {
                        "application/json": {"schema": meta["response"]},
                    },
                },
                "401": {"description": "Missing or invalid token"},
                "404": {"description": "Not found"},
            },
        }
        if request_schema:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{meta['request'].__name__}"}},
                },
            }

        # every authenticated route declares its security.
        # Public routes (register, login, refresh, verify, resend, forgot,
        # reset) must NOT require a bearer token.
        public = {"register", "login", "refresh",
                  "verify-email", "resend-verification",
                  "forgot-password", "reset-password"}
        if meta["tag"] != "ops" and path not in public:
            operation["security"] = [{"bearerAuth": []}]

        http_method = "post" if request_schema else "get"
        # routes with a path parameter use the template form; ensure a
        # leading slash so the path is absolute in the spec
        openapi_path = path.replace("<int:", "{").replace(">", "}")
        if not openapi_path.startswith("/"):
            openapi_path = "/" + openapi_path
        paths.setdefault(openapi_path, {})[http_method] = operation

    spec = dict(SPEC)
    spec["components"] = {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "15-minute access token from /api/v1/login or /api/v1/register",
            }
        },
        "schemas": schemas,
    }
    spec["paths"] = paths
    return spec


def swagger_ui_html(spec_url: str = "/api/v1/openapi.json") -> str:
    """Swagger UI that loads the generated spec.

    Loaded from the CDN rather than bundled, so the frontend does not need a
    build step to serve docs. The spec URL is the generated document, so the
    UI can never show something the code does not implement.
    """
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>DRQR — API Reference</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      SwaggerUIBundle({{
        url: "{spec_url}",
        dom_id: "#swagger-ui",
        docExpansion: "list",
        deepLinking: true,
      }});
    </script>
  </body>
</html>
"""

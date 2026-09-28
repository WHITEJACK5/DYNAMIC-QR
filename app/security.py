"""Security response headers (Phase 4b).

The directive requires `Content-Security-Policy`, `X-Content-Type-Options`,
`X-Frame-Options` and `Strict-Transport-Security`. It names flask-talisman
"or equivalent"; this is the equivalent, written out explicitly because the
policy has to match what this app actually serves, and because a header
generator that cannot be read is a header nobody can audit.

The policy is derived from measurement, not assumption:

  * No page loads JavaScript from a CDN, so script-src needs no external host.
  * The frontend is still raw multi-page HTML with inline event handlers
    (33 of them), one inline <script> in dashboard.html and inline <style>
    blocks, so 'unsafe-inline' is currently REQUIRED for script/style. It is
    the weakest link in this policy and Phase 8 (React + TS build) is what
    removes it. It is called out here rather than hidden.
  * Google Fonts is genuinely used (preconnect + stylesheet on every page),
    so style-src/font-src must allow those two origins.
  * QR previews are base64 data: URIs, so img-src needs data:.

HSTS is only sent over HTTPS: sending it on plain HTTP would pin a host to TLS
on a dev machine that has none. Behind the nginx reverse proxy the scheme
comes from the X-Forwarded-Proto header, which deploy/nginx.conf sets on every
location block.

Referrer-Policy is no-referrer. That is not in the directive, but it is the
other half of the Phase 4a fix: a token no longer travels in the query
string, and this stops full URLs leaking to any third party the page links to.
"""
from flask import request

# Origins the frontend genuinely loads from. Keep this list minimal — every
# entry is an external party that can run code or observe the visitor.
FONT_CSS = "https://fonts.googleapis.com"
FONT_FILES = "https://fonts.gstatic.com"

CSP_DIRECTIVES = (
    "default-src 'self'",
    # 'unsafe-inline' required by the current raw-HTML frontend (Phase 8
    # removes it). No external script host: no CDN is used.
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline' " + FONT_CSS,
    "font-src 'self' " + FONT_FILES,
    # base64 QR previews are inline images
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)

CSP = "; ".join(CSP_DIRECTIVES)

HSTS = "max-age=31536000; includeSubDomains"

# Applied to every response, HTML or not.
STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-DNS-Prefetch-Control": "off",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": CSP,
}


def _is_https() -> bool:
    try:
        if request.is_secure:
            return True
        # Trust the reverse proxy's scheme header (nginx sets it; see
        # deploy/nginx.conf). X-Forwarded-Proto is a comma list when a
        # request passed several proxies — the left-most is the client-facing
        # one, so take the first entry.
        proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
        return proto == "https"
    except Exception:
        return False


def apply_security_headers(resp):
    """Attach the policy to a response. Returns it, for chaining."""
    for header, value in STATIC_HEADERS.items():
        resp.headers.setdefault(header, value)
    if _is_https():
        resp.headers.setdefault("Strict-Transport-Security", HSTS)
    return resp

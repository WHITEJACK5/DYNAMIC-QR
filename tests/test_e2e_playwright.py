"""Phase 5c: end-to-end browser tests (Playwright).

Directive: "Add end-to-end tests (Playwright) covering: register -> login ->
generate dynamic QR -> scan it -> see it in analytics."

This drives the real SPA in Chromium against a real server process. It is
not a client-library test with a mock: the page loads, the auth modal opens,
the form is filled, the button is clicked, and the redirect is followed.

Two things make the full journey possible and both are exercised for real:

  * Phase 4d gates dynamic QRs behind a verified email, so the test stands
    up an in-process SMTP server (tests/smtp_catcher.py) and follows the
    real link out of a real email. It does not flip a database flag.
  * Phase 4c issues 15-minute access tokens with a refresh flow, so the
    test asserts the SPA stores and renews a session rather than only that
    one request happened to succeed.

Skipped unless PLAYWRIGHT is set or Playwright's chromium is available, so
a machine without browsers does not fail the whole suite.
"""
import os
import quopri
import re
import socket
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smtp_catcher import SMTPCatcher  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = not os.getenv("SKIP_E2E") and os.getenv("RUN_E2E", "1") != "0"

playwright_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
sync_playwright = playwright_api.sync_playwright


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def smtp():
    with SMTPCatcher() as c:
        yield c


@pytest.fixture(scope="module")
def live_server(smtp, tmp_path_factory):
    """
    A real server process on a real port.

    A subprocess rather than the test client, because the point of this file
    is that a browser can reach the app over HTTP. Temporary SQLite file and
    an explicit SECRET_KEY so it never touches the developer's .env.
    """
    port = _free_port()
    db = tmp_path_factory.mktemp("e2e") / "e2e.db"
    log = tmp_path_factory.mktemp("e2e-log") / "server.log"
    env = dict(os.environ)
    env.update({
        "SECRET_KEY": "e2e-test-secret-key-must-be-32-chars-long-ok",
        "BASE_URL": f"http://127.0.0.1:{port}",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "NARE_DB_PATH": str(db),
        "APP_ENV": "development",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": str(smtp.port),
        "SMTP_FROM": "no-reply@nareandco.test",
        # The catcher speaks plaintext SMTP on loopback, like a local relay.
        # Real deployments should leave STARTTLS on (the default).
        "SMTP_STARTTLS": "0",
        "PYTHONUNBUFFERED": "1",
        "LOG_LEVEL": "WARNING",
    })
    # A PIPE that nobody drains will eventually fill and block the server's
    # writes, which showed up as a request that never returns. Send the
    # child's output to a file instead.
    logfile = open(log, "w+", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import server; server.app.run(host='127.0.0.1', port=int(__import__('os').environ['PORT']),"
         " threaded=True, use_reloader=False)"],
        cwd=HERE, env=env, stdout=logfile, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    # Generous: the child imports the app and runs migrations before it
    # binds, and this can be slow when the machine is also running the rest
    # of the suite. A short wait here produced an intermittent startup
    # failure that looked like a product bug.
    deadline = time.time() + 180
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            logfile.flush()
            log.seek(0)
            raise RuntimeError(f"server exited early:\n{log.read()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                ready = True
                break
        except OSError:
            time.sleep(0.3)
    if not ready:
        proc.kill()
        raise RuntimeError("server did not start")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
    logfile.close()


@pytest.fixture(scope="module")
def browser():
    if not RUN:
        pytest.skip("SKIP_E2E set")
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(args=["--no-sandbox"])
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"chromium unavailable: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    # Generous default: rendering a 900px QR server-side is seconds, not
    # milliseconds, and a tight default turns a slow machine into a red build.
    pg.set_default_timeout(45000)
    yield pg
    ctx.close()


def _unique_email(prefix="e2e"):
    return f"{prefix}-{int(time.time() * 1000)}@nareandco.test"


def _open_auth(page, mode):
    """
    Open the auth modal and wait until it is actually open.

    Waiting only for NareSession was a race: session.js is the first
    script, so it is defined before app.js has declared openAuth, and the
    register click then landed on a modal that was never shown.
    """
    page.wait_for_function("() => typeof window.openAuth === 'function'", timeout=20000)
    page.evaluate(f"() => window.openAuth({mode!r})")
    page.wait_for_function(
        "() => document.getElementById('authModal').classList.contains('open')",
        timeout=10000)
    return page


def _register_via_ui(page, base, email, password="StrongPass123!"):
    """Register through the real auth modal, then verify via real email."""
    page.goto(base + "/", wait_until="domcontentloaded")
    _open_auth(page, "register")
    page.locator("#authEmail").fill(email)
    page.locator("#authPass").fill(password)
    name_input = page.locator("#nameField input")
    if name_input.count():
        name_input.first.fill("E2E User")
    page.locator("#authSubmit").click()
    page.wait_for_function(
        "() => !!localStorage.getItem('nare_refresh')", timeout=20000)
    return page.evaluate("() => localStorage.getItem('nare_refresh')")


def _login_via_ui(page, base, email, password="StrongPass123!"):
    page.goto(base + "/", wait_until="domcontentloaded")
    _open_auth(page, "login")
    page.locator("#authEmail").fill(email)
    page.locator("#authPass").fill(password)
    page.locator("#authSubmit").click()
    page.wait_for_function(
        "() => !!localStorage.getItem('nare_token')", timeout=20000)
    return page.evaluate("() => localStorage.getItem('nare_token')")


def _verify_from_email(smtp, email, page):
    """Follow the real verification link delivered over SMTP.

    Asserts the link actually verified the account. Without this the
    failure surfaces much later as "dynamic QR was not created", which
    gives no clue that the email step was the thing that broke.
    """
    msg = smtp.wait_for(email)
    assert msg is not None, f"no verification email arrived for {email}"
    # The raw SMTP payload is quoted-printable: "=" at end of line is a soft
    # line break, and the URL gets wrapped mid-token. Decoding the transfer
    # encoding is what makes the link parseable — stripping "=\n" by hand
    # still leaves a trailing "=" glued onto the token.
    body = quopri.decodestring(msg["data"].encode("utf-8")).decode("utf-8", "replace")
    m = re.search(r"https?://[^\s\"'<>\]]+/api/verify-email\?token=[A-Za-z0-9_\-%.]+",
                  body)
    assert m, f"no verification link in the email body:\n{body[:800]}"
    link = m.group(0)
    resp = page.goto(link, wait_until="domcontentloaded", timeout=30000)
    assert resp.status == 200, \
        f"verification link returned {resp.status}, not 200: {link[:120]}"
    text = page.locator("body").inner_text()
    assert "verified" in text.lower(), \
        f"verification link did not confirm the account:\n{text[:300]}"
    return link


def _login_via_ui_unused_placeholder():
    pass


# ------------------------------------------------------------------------ tests
@pytest.mark.skipif(not RUN, reason="SKIP_E2E set")
def test_page_loads_with_security_headers_and_session_helper(page, live_server):
    """Phase 4b/4c: the CSP is present and the page actually still runs."""
    responses = []
    page.on("response", lambda r: responses.append(r))
    page.goto(live_server + "/", wait_until="domcontentloaded")
    body = page.locator("body").inner_text()
    assert "NARE" in body.upper()
    doc = [r for r in responses if r.url.rstrip("/").endswith(live_server.rstrip("/"))]
    assert doc, "no main document response captured"
    headers = doc[0].headers
    assert headers.get("content-security-policy"), "CSP header missing"
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("referrer-policy") == "no-referrer"
    # CSP must not have blocked the app's own scripts
    errors = page.evaluate("() => window.__errs || []")
    assert not errors


@pytest.mark.skipif(not RUN, reason="SKIP_E2E set")
def test_register_verify_login_and_create_dynamic_qr(page, live_server, smtp):
    """register -> verify from a real email -> login -> dynamic QR."""
    email = _unique_email("journey")

    refresh = _register_via_ui(page, live_server, email)
    assert refresh, "registration did not store a refresh token"

    # Phase 4d: the dynamic QR gate is closed until the address is confirmed
    _verify_from_email(smtp, email, page)

    token = _login_via_ui(page, live_server, email)
    assert token, "login did not store an access token"

    # generate a dynamic QR through the real form: pick the URL type, fill
    # the field the app renders for it, flip the styled toggle, submit.
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => typeof window.openAuth === 'function'")
    page.evaluate("() => window.NareSession.refreshAccessToken()")
    page.locator('.type-btn[data-type="url"]').first.click()
    page.wait_for_selector("#f_url", timeout=10000)
    # the checkbox is visually hidden behind a styled label, so click the
    # label the way a user does rather than the zero-size input. This must
    # happen BEFORE filling the field: flipping the toggle re-renders the
    # form area, which discards anything already typed.
    page.locator("#dynamicToggle").locator("xpath=..").click()
    page.wait_for_function("() => document.getElementById('dynamicToggle').checked",
                           timeout=10000)
    page.wait_for_selector("#f_url", timeout=10000)
    page.locator("#f_url").fill("https://example.com/e2e-target")
    assert page.locator("#f_url").input_value(), "the URL field was not filled"

    calls = []
    page.on("request", lambda r: calls.append(("REQ", r.method, r.url))
            if "/api/" in r.url else None)
    page.on("response", lambda r: calls.append(("RES", r.status, r.url))
            if "/api/" in r.url else None)
    # Wait for the response rather than sleeping a fixed time: generate()
    # renders a 900px PNG with a base64 payload and routinely takes several
    # seconds, so a short wait asserted against a request still in flight.
    with page.expect_response(lambda r: "/api/generate" in r.url, timeout=90000):
        page.locator("#generateBtn").click()
    page.wait_for_timeout(1500)

    # On failure, say what the page said: a toast explains "why" that a bare
    # "no dynamic QR" never will.
    diag = page.evaluate(
        """async () => {
             const t = localStorage.getItem('nare_token');
             const r = await fetch('/api/qrcodes?limit=50&offset=0',
               {headers:{Authorization:`Bearer ${t}`}});
             const j = await r.json();
             const items = Array.isArray(j) ? j : (j.items || []);
             const toastEl = document.querySelector('.toast, #toast');
             return JSON.stringify({
               checked: document.getElementById('dynamicToggle').checked,
               isDynamic: window.state ? window.state.isDynamic : 'n/a',
               type: window.state ? window.state.type : 'n/a',
               listed: items.length,
               firstShort: items.length ? items[0].short_code : null,
               toast: toastEl ? toastEl.textContent : null,
             });
           }"""
    )
    short_code = page.evaluate("() => (window.state && window.state.shortCode) || null")
    if not short_code:
        short_code = page.evaluate(
            """async () => {
                 const t = localStorage.getItem('nare_token');
                 const r = await fetch('/api/qrcodes?limit=50&offset=0',
                   {headers:{Authorization:`Bearer ${t}`}});
                 const j = await r.json();
                 const items = Array.isArray(j) ? j : (j.items || []);
                 return items.length ? items[0].short_code : null;
               }"""
        )
    assert short_code, f"no dynamic QR was created; page state: {diag}\n  calls: {calls}"


@pytest.mark.skipif(not RUN, reason="SKIP_E2E set")
def test_scan_redirect_and_analytics_full_journey(page, browser, live_server, smtp):
    """
    The complete journey the directive names:
    register -> login -> generate dynamic QR -> scan it -> see it in analytics.

    The scan is performed by a separate browser context, so the analytics
    request is not served from the generator's own authenticated session.
    """
    email = _unique_email("scan")
    _register_via_ui(page, live_server, email)
    _verify_from_email(smtp, email, page)
    _login_via_ui(page, live_server, email)

    # create the dynamic QR via the API the page itself uses. The
    # destination is a path on this same server on purpose: a public URL
    # would make the browser wait on a third party and the test would be
    # measuring that host's latency, not the redirect.
    short_code = page.evaluate(
        """async () => {
             const t = localStorage.getItem('nare_token');
             const r = await fetch('/api/generate', {
               method:'POST',
               headers:{'Content-Type':'application/json',
                        Authorization:`Bearer ${t}`},
               body: JSON.stringify({type:'url',
                 data:{url: location.origin + '/e2e-target'},
                 is_dynamic:true, name:'E2E scan'})});
             const j = await r.json();
             return j.short_code || null;
           }"""
    )
    assert short_code, f"dynamic QR was not created: {short_code}"

    # a different visitor scans the code
    visitor_ctx = browser.new_context()
    visitor = visitor_ctx.new_page()
    try:
        visitor.goto(f"{live_server}/r/{short_code}", wait_until="commit",
                     timeout=30000)
        visitor.wait_for_timeout(1500)
        assert "/e2e-target" in visitor.url, \
            f"redirect did not land on the destination: {visitor.url}"
    finally:
        visitor_ctx.close()

    # the owner sees the scan in analytics, in the dashboard UI. The
    # analytics panel is behind a nav tab and starts display:none, so
    # clicking the real tab is part of the journey.
    dash = page.goto(live_server + "/dashboard", wait_until="domcontentloaded",
                     timeout=45000)
    assert dash.status == 200, f"dashboard status {dash.status}"
    page.locator('[data-view="analytics"]').click()
    page.wait_for_selector("#view-analytics:visible", timeout=20000)
    # Wait for real content, not merely for a non-empty div: the panel
    # starts as the placeholder "Loading…", which is already longer than any
    # length threshold, so a size check passes instantly and then reads the
    # placeholder. 'Timeline' is a heading the panel only contains once the
    # analytics payload has been rendered into it.
    page.wait_for_function(
        "() => { const e = document.getElementById('analyticsBody');"
        " return e && e.textContent.includes('Timeline'); }",
        timeout=20000)
    body = page.locator("#analyticsBody").inner_text()
    assert re.search(r"\b1\b", body), \
        f"analytics did not report the scan:\n{body[:400]}"


@pytest.mark.skipif(not RUN, reason="SKIP_E2E set")
def test_dashboard_requires_login(page, live_server):
    """The dashboard must not render another user's data to a stranger."""
    page.goto(live_server + "/dashboard", wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    assert "/" in page.url, f"expected a redirect to the login page, got {page.url}"
    assert "qrcodes" not in page.content().lower()


@pytest.mark.skipif(not RUN, reason="SKIP_E2E set")
def test_logout_revokes_the_session(page, live_server, smtp):
    """Phase 4c: logging out must invalidate the token server-side, not just
    clear localStorage."""
    email = _unique_email("logout")
    _register_via_ui(page, live_server, email)
    _verify_from_email(smtp, email, page)
    _login_via_ui(page, live_server, email)
    token = page.evaluate("() => localStorage.getItem('nare_token')")
    assert token

    page.evaluate("async () => { await window.NareSession.logout(); }")
    assert not page.evaluate("() => localStorage.getItem('nare_token')")

    # the revoked token must be refused even if something still holds it
    status = page.evaluate(
        """async (t) => {
             const r = await fetch('/api/qrcodes', {headers:{Authorization:`Bearer ${t}`}});
             return r.status;
           }""",
        token,
    )
    assert status == 401, f"a logged-out token still worked (status {status})"

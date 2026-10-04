"""Capture screenshots of every working page and state in the app.

The React build is a skeleton; the real UI is the raw HTML/JS frontend
served by Flask. This drives the actual running app with Playwright and
saves one PNG per page/state into docs/screenshots/.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(SHOTS, exist_ok=True)

env = dict(os.environ)
env.update({
    "SECRET_KEY": "capture-secret-key-must-be-32-chars-long",
    "BASE_URL": "http://localhost:5000",
    "DATABASE_URL": "sqlite:///" + os.path.join(ROOT, "data", "capture.db"),
    "FLASK_DEBUG": "false",
})

proc = subprocess.Popen(
    [sys.executable, "server.py"], cwd=ROOT, env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)

EMAIL = f"demo{int(time.time())}@example.com"
PWD = "StrongPass123!"


def shot(page, name, width=1280, height=800, action=None):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": width, "height": height})
        pg = ctx.new_page()
        pg.goto(f"http://localhost:5000{page}", wait_until="networkidle")
        pg.wait_for_timeout(1200)
        if action:
            action(pg)
            pg.wait_for_timeout(1200)
        pg.screenshot(path=os.path.join(SHOTS, name), full_page=False)
        b.close()
    print(f"  {name}")


try:
    # 1. Generator (homepage) — the main interface
    shot("/", "01-generator.png")

    # 2. Login modal
    def open_login(pg):
        pg.evaluate("() => window.openAuth('login')")
    shot("/", "02-login-modal.png", action=open_login)

    # 3. Register modal
    def open_register(pg):
        pg.evaluate("() => window.openAuth('register')")
    shot("/", "03-register-modal.png", action=open_register)

    # 4. Register a real user so we can reach authenticated pages
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        pg.goto("http://localhost:5000/", wait_until="networkidle")
        pg.evaluate("() => window.openAuth('register')")
        pg.wait_for_timeout(600)
        pg.fill("#authEmail", EMAIL)
        pg.fill("#authPass", PWD)
        nf = pg.locator("#nameField input")
        if nf.count():
            nf.first.fill("Demo User")
        pg.click("#authSubmit")
        pg.wait_for_function(
            "() => !!localStorage.getItem('dr_token')", timeout=15000)
        b.close()
    print("  registered + logged in")

    # 5. Generator while logged in (shows user state)
    shot("/", "04-generator-authenticated.png")

    # 6. Generate a dynamic QR and capture the result
    def gen_qr(pg):
        pg.fill("#urlInput", "https://example.com/campaign")
        pg.click("#generateBtn")
        pg.wait_for_timeout(2500)
    shot("/", "05-qr-generated.png", action=gen_qr)

    # 7. Dashboard — QR management
    shot("/dashboard", "06-dashboard.png")

    # 8. Dashboard — analytics view
    def analytics_view(pg):
        el = pg.locator('[data-view="analytics"]')
        if el.count():
            el.first.click()
            pg.wait_for_timeout(1500)
    shot("/dashboard", "07-analytics.png", action=analytics_view)

    # 9. Dashboard — folders view
    def folders_view(pg):
        el = pg.locator('[data-view="folders"]')
        if el.count():
            el.first.click()
            pg.wait_for_timeout(1200)
    shot("/dashboard", "08-folders.png", action=folders_view)

    # 10. Pricing page
    shot("/pricing", "09-pricing.png")

    # 11. Manual page
    shot("/manual", "10-manual.png")

    # 12. API docs (generated OpenAPI/Swagger UI)
    shot("/api/v1/docs", "11-api-docs.png")

    print("all screenshots captured")
finally:
    proc.terminate()
    proc.wait(timeout=10)

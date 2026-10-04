"""Capture real screenshots and a demo video of the running app.

Serves the built frontend over HTTP and drives it with Playwright.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "docs", "screenshots")
VIDEOS = os.path.join(ROOT, "docs", "videos")
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(VIDEOS, exist_ok=True)

env = dict(os.environ)
env["SECRET_KEY"] = "capture-secret-key-must-be-32-chars-long"
env["BASE_URL"] = "http://localhost:5000"
env["DATABASE_URL"] = "sqlite:///" + os.path.join(ROOT, "data", "capture.db")
env["FLASK_DEBUG"] = "false"

proc = subprocess.Popen(
    [sys.executable, "server.py"], cwd=ROOT, env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(4)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=VIDEOS,
        )
        page = ctx.new_page()

        # Generator / homepage
        page.goto("http://localhost:5000/", wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOTS, "generator.png"))

        # Dashboard
        page.goto("http://localhost:5000/dashboard", wait_until="networkidle")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.join(SHOTS, "dashboard.png"))

        # API docs
        page.goto("http://localhost:5000/api/v1/docs", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, "api-docs.png"))

        # Manual
        page.goto("http://localhost:5000/manual", wait_until="networkidle")
        page.wait_for_timeout(1500)
        page.screenshot(path=os.path.join(SHOTS, "manual.png"))

        ctx.close()
        browser.close()
    print("captured screenshots and video")
finally:
    proc.terminate()
    proc.wait(timeout=10)

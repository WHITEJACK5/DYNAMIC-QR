"""Production WSGI entrypoint (Phase 2e).

Local dev keeps `python app.py` (fresh-clone contract, SQLite, 127.0.0.1).
Any real deployment serves THIS module with gunicorn behind a reverse
proxy, e.g.::

    gunicorn wsgi:application -w 4 -b 127.0.0.1:5000

`app.run()` inside app.py is dev-only and must never be the production
entrypoint. No Postgres/Redis wiring yet — those land in Phase 2f-2h
(rate limit / jobs / cache) and Phase 3 (data layer).
"""
from app import app as application  # noqa: F401 — WSGI callable

# gunicorn also accepts `wsgi:app`; keep both names working.
app = application

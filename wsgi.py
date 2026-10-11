"""Production WSGI entrypoint (Phase 2e).

Local dev keeps `python server.py` (fresh-clone contract, SQLite, 127.0.0.1).
Any real deployment serves THIS module with gunicorn, e.g.::

    gunicorn wsgi:application -w 4 -b 127.0.0.1:5000     # behind your own nginx
    gunicorn wsgi:application -w 4 -b 0.0.0.0:$PORT     # platform-managed dyno

`app.run()` inside server.py is dev-only and must never be the production
entrypoint — it is a single-threaded, non-forking WSGI dev server with no
request timeouts to speak of. PostgreSQL, Redis, S3 and rate limiting are all
wired through this same entrypoint; the only decision is whether the
environment supplies them.
"""
from server import app as application  # noqa: F401 — WSGI callable

# gunicorn also accepts `wsgi:app`; keep both names working.
app = application

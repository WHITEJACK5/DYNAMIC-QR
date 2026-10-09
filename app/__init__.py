"""DRQR application package — the layered layout the architecture requires.

    app/
      routes/        thin HTTP handlers (parse request -> call service/repo -> respond)
      services/      business logic that is not a single table's access
      repositories/  all database access, user-scoped, dialect-agnostic
      models.py      SQLAlchemy models — the schema of record
      schemas.py     Pydantic request schemas for every JSON route
      utils.py       pure helpers (QR content builders, colour parsing, validation)
      db.py          engine + session factory, dialect-specific pooling
      migrations.py  programmatic Alembic upgrade/downgrade
      cache.py       read-through cache (Redis, in-memory fallback)
      ratelimit.py   rate limiting (Redis, in-memory fallback)
      jobs.py        background jobs (RQ, thread fallback)
      storage.py     logo storage (S3-compatible object storage)
      pagination.py  shared limit/offset parsing

`server.py` at the repository root is the executable entrypoint
(`python server.py`); `wsgi.py` exposes the WSGI callable for gunicorn.
This package deliberately does NOT create the Flask app — that stays in
server.py until the route handlers move into app/routes/.
"""

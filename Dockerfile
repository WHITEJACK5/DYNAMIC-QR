# NARE & CO. — production image (Phase 6a)
#
# Served by gunicorn (wsgi:application) behind the reverse proxy, never by
# app.run(). Postgres and Redis are separate services; see docker-compose.yml.
#
# Design notes:
#   * Pinned exact versions in requirements.txt, so the image is reproducible.
#   * Non-root by default. Containers that run as root are one leaked
#     container-escape away from owning the host.
#   * No secret is baked in. SECRET_KEY arrives from the environment (the
#     host's secret store in staging/production) and app/config.py refuses to
#     start without it there.
#   * .dockerignore keeps .git, .env, local databases and caches out of the
#     build context, so a developer's secrets cannot end up in a layer.

# ---------------------------------------------------------------- builder
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for any wheel that needs compiling; removed with the build
# stage so they never reach the runtime image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------- runtime
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000 \
    WEB_CONCURRENCY=4 \
    GUNICORN_TIMEOUT=60 \
    APP_ENV=production

# libpq for psycopg2 at runtime, curl for the container healthcheck.
# tini reaps zombies and forwards signals, so gunicorn actually receives
# SIGTERM on `docker stop` and drains in-flight requests.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl tini \
 && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user with a fixed uid/gid so bind-mounted volumes
# have predictable ownership.
RUN groupadd --system --gid 1001 nare \
 && useradd --system --uid 1001 --gid nare --home-dir /app --shell /usr/sbin/nologin nare

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

COPY --chown=nare:nare . /app

# The app writes to data/ (SQLite fallback) and uploads/; both are volumes
# in compose, and object storage is the system of record for logos in
# production, so this is only the dev-mode fallback path.
RUN mkdir -p /app/data /app/uploads && chown -R nare:nare /app/data /app/uploads

USER nare

EXPOSE 8000

# /api/health is a real dependency check, not just "the process is up": it
# reports the resolved database.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "gunicorn wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY} --timeout ${GUNICORN_TIMEOUT} --access-logfile - --error-logfile -"]
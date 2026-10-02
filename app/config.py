"""Environment + filesystem configuration (extracted from server.py).

Imported by app.extensions, the route blueprints, and server.py, so there is
exactly one place that reads the environment and generates/persists the
SECRET_KEY. Logging is configured here BEFORE the first logger use, which is
the Phase 1c fix — keep that ordering.
"""
import logging
import os
import secrets

from dotenv import load_dotenv

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _looks_like_production() -> bool:
    """True when running on a hosting platform, or declared explicitly.

    Detected from the variables those platforms set rather than from a
    heuristic, so a container that is not on a known platform is treated as
    development and keeps working out of the box. Must be defined before
    load_dotenv() so the .env decision can use it.
    """
    explicit = os.getenv("APP_ENV", "").strip().lower()
    if explicit in ("production", "prod", "staging"):
        return True
    platform_markers = ("RENDER", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME",
                        "DYNO", "HEROKU_APP_NAME", "KUBERNETES_SERVICE_HOST")
    return any(os.getenv(m, "").strip() for m in platform_markers)


# Logging first (Phase 1c): the production .env check and the SECRET_KEY
# bootstrap below both log, so this must come before either of them.
# Phase 7b: JSON structured logging, installed here because every module
# imports this file first.
from app.logging_config import install_json_logging

install_json_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    service="nare",
    env="production" if _looks_like_production() else "development",
)
logger = logging.getLogger("nare")

# Phase 7a: Sentry. Initialised here, before any route can raise, and
# fail-safe — without SENTRY_DSN this is a no-op.
from app import sentry as _sentry  # noqa: E402

_sentry.init()

IS_PRODUCTION = _looks_like_production()

# Phase 4g: in staging/production secrets come from the platform's secret
# store, which injects environment variables. Loading a .env file there
# would let a stale file — one baked into the image, or left over from a
# previous build — silently shadow the injected value, so it is not loaded.
# Development is unaffected: a fresh clone still works with zero setup.
if IS_PRODUCTION:
    _env_file = os.path.join(APP_DIR, ".env")
    if os.path.exists(_env_file):
        logger.warning(
            "[NARE & CO.] Ignoring %s: secrets in staging/production must come "
            "from the host's secret store, not a file. If this file is baked "
            "into the image, remove it from the build.", _env_file
        )
else:
    load_dotenv()

# Data location. Overridable so a container can mount a volume and so the
# end-to-end tests can run against a throwaway database instead of the
# developer's data/nare.db.
DB_PATH = os.getenv("NARE_DB_PATH") or os.path.join(APP_DIR, "data", "nare.db")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
STATIC_DIR = os.path.join(APP_DIR, "static")
FRONTEND_DIR = os.path.join(APP_DIR, "frontend")

os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)
for _d in [os.path.join(APP_DIR, "data"), UPLOAD_DIR]:
    _keep = os.path.join(_d, ".gitkeep")
    if not os.path.exists(_keep):
        try:
            open(_keep, "a").close()
        except Exception as e:
            logging.warning("Could not create .gitkeep in %s: %s", _d, e)

# --- Security: SECRET_KEY must not be hardcoded ---
#
# Phase 4g: in staging/production the secret is injected by the host's
# secret store (Render/Railway/Fly environment variables, AWS Secrets
# Manager). Local development keeps the zero-setup behaviour of generating
# a key and persisting it to .env.
#
# What must never happen: a production deploy with no SECRET_KEY silently
# generating one and writing it into the container filesystem. That key dies
# with the container (invalidating every session on the next restart), it
# sits on disk where a secret store was supposed to supply it, and the
# deploy looks healthy. So production refuses to start instead.
SECRET_KEY = os.getenv("SECRET_KEY")
JWT_SECRET = os.getenv("JWT_SECRET") or SECRET_KEY
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "SECRET_KEY is not set and this looks like a production or "
            "staging environment.\n"
            "Set it in your host's secret store — the app reads secrets from "
            "the environment, never from a file:\n"
            "  Render:    Dashboard > your service > Environment > Add secret\n"
            "  Railway:   project > Variables > add SECRET_KEY\n"
            "  Fly.io:    fly secrets set SECRET_KEY=...\n"
            "  AWS:       SSM/Secrets Manager, exported by the task definition\n"
            "Generate one with: python -c \"import secrets; "
            "print(secrets.token_hex(32))\"\n"
            "Refusing to start: generating a key here would store it on the "
            "container filesystem, where it is lost on every restart."
        )
    # Generate and persist for local development (so tokens survive restart)
    generated = secrets.token_hex(32)
    try:
        _env_path = os.path.join(APP_DIR, ".env")
        if not os.path.exists(_env_path):
            with open(_env_path, "w") as f:
                f.write(f"SECRET_KEY={generated}\nBASE_URL=http://localhost:5000\nHOST=127.0.0.1\nPORT=5000\nFLASK_DEBUG=false\nALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000\n")
            logger.info("[NARE & CO.] Created .env with fresh SECRET_KEY at %s", _env_path)
        else:
            # append if .env exists but no key
            with open(_env_path, "a") as f:
                f.write(f"\nSECRET_KEY={generated}\n")
            logger.info("[NARE & CO.] Appended SECRET_KEY to %s", _env_path)
    except Exception as e:
        logger.warning("Could not write .env: %s", e)
    SECRET_KEY = generated
    JWT_SECRET = SECRET_KEY
    logging.warning("[NARE & CO.] SECRET_KEY was not set — generated and persisted to .env (development only)")
    logger.info("SECRET_KEY generated and saved to .env - restart to use persistent key (or set manually)")
else:
    if len(SECRET_KEY) < 32:
        if IS_PRODUCTION:
            raise RuntimeError(
                f"SECRET_KEY is only {len(SECRET_KEY)} characters; at least 32 "
                "are required. A short key is a guessable key."
            )
        logging.warning("[NARE & CO.] SECRET_KEY is short (<32 chars) — use a long random string.")
        logger.warning("SECRET_KEY too short - generate: python -c \"import secrets; print(secrets.token_hex(32))\"")

# In production the secret store must be the only source. Warn if a .env is
# also present so a stale file baked into the image cannot shadow an
# injected secret unnoticed.
if IS_PRODUCTION and os.path.exists(os.path.join(APP_DIR, ".env")):
    logger.warning(
        "[NARE & CO.] A .env file exists but secrets are being read from the "
        "environment. Ensure it is not baked into the image."
    )

JWT_ALGO = "HS256"
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")

# CORS — restrict to allowed origins
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

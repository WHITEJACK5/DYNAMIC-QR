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

load_dotenv()

# Logging first: the SECRET_KEY bootstrap below logs (Phase 1c).
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nare")

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(APP_DIR, "data", "nare.db")
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
            logging.warning(f"Could not create .gitkeep in {_d}: {e}")

# --- Security: SECRET_KEY must not be hardcoded ---
SECRET_KEY = os.getenv("SECRET_KEY")
JWT_SECRET = os.getenv("JWT_SECRET") or SECRET_KEY
if not SECRET_KEY:
    # Generate and persist for personal fresh installs (so tokens survive restart)
    generated = secrets.token_hex(32)
    try:
        _env_path = os.path.join(APP_DIR, ".env")
        if not os.path.exists(_env_path):
            with open(_env_path, "w") as f:
                f.write(f"SECRET_KEY={generated}\nBASE_URL=http://localhost:5000\nHOST=127.0.0.1\nPORT=5000\nFLASK_DEBUG=false\nALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000\n")
            print(f"[NARE & CO.] Created .env with fresh SECRET_KEY at {_env_path}")
        else:
            # append if .env exists but no key
            with open(_env_path, "a") as f:
                f.write(f"\nSECRET_KEY={generated}\n")
            print(f"[NARE & CO.] Appended SECRET_KEY to {_env_path}")
    except Exception as e:
        logger.warning(f"Could not write .env: {e}")
    SECRET_KEY = generated
    JWT_SECRET = SECRET_KEY
    logging.warning("[NARE & CO.] SECRET_KEY was not set — generated and persisted to .env")
    print("[INFO] SECRET_KEY generated and saved to .env — restart to use persistent key (or set manually)")
else:
    if len(SECRET_KEY) < 32:
        logging.warning("[NARE & CO.] SECRET_KEY is short (<32 chars) — use a long random string.")
        print("[WARN] SECRET_KEY too short — generate: python -c \"import secrets; print(secrets.token_hex(32))\"")

JWT_ALGO = "HS256"
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true", "yes")

# CORS — restrict to allowed origins
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

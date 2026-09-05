import os
import re
import json
import base64
import sqlite3
import secrets
import datetime
import string
import logging
from io import BytesIO
from functools import wraps
from urllib.parse import urlparse

import jwt
import qrcode
import requests
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer, CircleModuleDrawer, GappedSquareModuleDrawer, RoundedModuleDrawer
)
from qrcode.image.styles.colormasks import SolidFillColorMask, RadialGradiantColorMask, SquareGradiantColorMask
from qrcode.image.svg import SvgPathImage
from PIL import Image, ImageDraw, ImageFont, ImageOps
from flask import Flask, request, jsonify, send_from_directory, g, redirect, send_file, abort
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

# Load env
load_dotenv()

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "data", "nare.db")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
STATIC_DIR = os.path.join(APP_DIR, "static")

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

# CORS â€” restrict to allowed origins
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
# For personal local use we allow credentials only for those origins
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
# Enable CORS with explicit origins
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nare")

# Rate limiting â€” simple in-memory (for production use Flask-Limiter + Redis)
_rate_store = {}  # {key: [timestamps]}
def _is_rate_limited(key, limit, window_sec):
    now = datetime.datetime.utcnow().timestamp()
    lst = _rate_store.get(key, [])
    # prune
    lst = [t for t in lst if now - t < window_sec]
    if len(lst) >= limit:
        _rate_store[key] = lst
        return True
    lst.append(now)
    _rate_store[key] = lst
    return False

def rate_limit(limit=5, window=60, key_func=None):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            try:
                k = key_func() if key_func else request.remote_addr or "unknown"
            except Exception:
                k = request.remote_addr or "unknown"
            endpoint_key = f"{f.__name__}:{k}"
            if _is_rate_limited(endpoint_key, limit, window):
                logger.warning(f"Rate limited {endpoint_key}")
                return jsonify({"error": "Too many requests. Please try again later."}), 429
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ---------------- DB ----------------
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    is_fresh = not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0
    db = get_db()
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT,
        created_at TEXT,
        is_premium INTEGER DEFAULT 0,
        twofa_enabled INTEGER DEFAULT 0,
        twofa_secret TEXT,
        reset_token TEXT,
        reset_expires TEXT
    )""")
    # migrate existing DB: add reset columns if missing
    try:
        cur.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN reset_expires TEXT")
    except Exception:
        pass
    cur.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS qrcodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        folder_id INTEGER,
        name TEXT,
        type TEXT,
        content TEXT,
        data_json TEXT,
        is_dynamic INTEGER,
        short_code TEXT UNIQUE,
        fg_color TEXT,
        bg_color TEXT,
        gradient TEXT,
        pattern TEXT,
        eye_style TEXT,
        frame_text TEXT,
        frame_color TEXT,
        logo_path TEXT,
        has_password INTEGER DEFAULT 0,
        password_hash TEXT,
        expiry_date TEXT,
        scan_limit INTEGER,
        scan_count INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id INTEGER,
        timestamp TEXT,
        ip TEXT,
        user_agent TEXT,
        device TEXT,
        browser TEXT,
        os TEXT,
        country TEXT,
        city TEXT,
        FOREIGN KEY(qr_id) REFERENCES qrcodes(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        config_json TEXT,
        created_at TEXT
    )""")
    db.commit()
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qr_short ON qrcodes(short_code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scans_qr ON scans(qr_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_qr_user ON qrcodes(user_id)")
        db.commit()
    except Exception as e:
        logger.warning(f"Index creation failed: {e}")
    db.close()
    if is_fresh:
        print(f"[NARE & CO.] Fresh DB created at {DB_PATH} â€” tables: users, qrcodes, scans, folders, templates")
        print(f"[NARE & CO.] Local DB ready for personal use â€” login + QR managing + analytics (SQLite)")
        logger.info(f"Fresh DB created at {DB_PATH}")
    else:
        try:
            _db = get_db()
            _cur = _db.cursor()
            _cur.execute("SELECT COUNT(*) FROM users")
            _u = _cur.fetchone()[0]
            _cur.execute("SELECT COUNT(*) FROM qrcodes")
            _q = _cur.fetchone()[0]
            _db.close()
            print(f"[NARE & CO.] DB loaded â€” {DB_PATH} â€” users:{_u} qrs:{_q}")
        except Exception as e:
            logger.warning(f"DB status check failed: {e}")

init_db()

# --------------- Helpers ---------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ',1)[1]
        if not token:
            token = request.cookies.get('token') or request.args.get('token')
        if not token:
            return jsonify({"error":"Missing token"}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            g.user_id = data['user_id']
            g.user_email = data['email']
        except jwt.ExpiredSignatureError:
            return jsonify({"error":"Token expired"}), 401
        except Exception as e:
            logger.warning(f"Invalid token: {e}")
            return jsonify({"error":"Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def optional_auth():
    token = None
    auth = request.headers.get('Authorization','')
    if auth.startswith('Bearer '):
        token = auth.split(' ',1)[1]
    if token:
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            return data['user_id']
        except Exception:
            return None
    return None

def get_base_url(req=None):
    if BASE_URL:
        return BASE_URL
    if req:
        return req.host_url.rstrip("/")
    try:
        return request.host_url.rstrip("/")
    except Exception:
        return "http://localhost:5000"

def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h)==3:
        h=''.join([c*2 for c in h])
    return tuple(int(h[i:i+2],16) for i in (0,2,4))

def generate_short_code(n=8):
    # Use 62-char alphabet for full entropy: 62^8 ~ 2.18e14
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(n))

def validate_email_format(email):
    # Basic regex first (permissive for personal/test domains like .local, .test)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False
    try:
        from email_validator import validate_email, EmailNotValidError
        validate_email(email, check_deliverability=False)
        return True
    except ImportError:
        return True
    except Exception:
        # If validator rejects but regex passes (e.g., .local), allow for personal use
        return True

def validate_password_strength(pwd):
    # Industry: >=8 chars, at least 3 of 4 categories
    if len(pwd) < 8:
        return False, "Password must be at least 8 characters"
    cats = 0
    if re.search(r"[A-Z]", pwd): cats += 1
    if re.search(r"[a-z]", pwd): cats += 1
    if re.search(r"\d", pwd): cats += 1
    if re.search(r"[^A-Za-z0-9]", pwd): cats += 1
    if cats < 3:
        return False, "Password must include 3 of: uppercase, lowercase, digit, special char"
    # also check common weak passwords
    weak = {"password", "12345678", "qwerty123", "letmein", "admin123"}
    if pwd.lower() in weak:
        return False, "Password is too common"
    return True, ""

def build_gs1_content(data):
    # Real GS1 Digital Link: https://id.gs1.org/01/<gtin>...
    # Accept gtin, lot, expiry, serial, etc.
    gtin = data.get("gtin") or data.get("content") or ""
    # if content already looks like GS1 Digital Link, return as is
    if gtin.startswith("http"):
        return gtin
    # if content has parentheses AI like (01)09506000134352(17)240105
    if gtin.startswith("("):
        # Convert AI format to digital link path: (01)X(10)Y â†’ /01/X/10/Y
        try:
            # parse (AI)value
            parts = re.findall(r"\((\d+)\)([^(]+)", gtin)
            if parts:
                path = "/".join([f"{ai}/{val.strip()}" for ai, val in parts])
                return f"https://id.gs1.org/{path}"
        except Exception as e:
            logger.warning(f"GS1 parse failed: {e}")
        return gtin
    # if gtin is plain 8/12/13/14 digits
    gtin_digits = re.sub(r"\D", "", gtin)
    if 8 <= len(gtin_digits) <= 14:
        # pad to 14 for GS1
        gtin14 = gtin_digits.zfill(14)
        extra = ""
        if data.get("lot"): extra += f"/10/{data['lot']}"
        if data.get("serial"): extra += f"/21/{data['serial']}"
        if data.get("expiry"): extra += f"/17/{data['expiry']}"
        return f"https://id.gs1.org/01/{gtin14}{extra}"
    # fallback
    return data.get("url") or data.get("content") or gtin or "https://id.gs1.org/"

def resolve_smart_url(qr_row, req):
    # Smart URL: data_json contains {"primaryUrl": "...", "rules": [{"condition":"android","url":"..."}]}
    try:
        data = json.loads(qr_row["data_json"]) if qr_row["data_json"] else {}
    except Exception:
        data = {}
    primary = data.get("primaryUrl") or data.get("url") or qr_row["content"]
    rules = data.get("rules")
    if isinstance(rules, str):
        # try parse lines like "device:android -> https://..."
        parsed = []
        for line in rules.splitlines():
            if "->" in line or "â†’" in line:
                sep = "->" if "->" in line else "â†’"
                cond, url = line.split(sep, 1)
                parsed.append({"condition": cond.strip().lower(), "url": url.strip()})
        rules = parsed
    if not isinstance(rules, list):
        return primary
    # detect
    ua = (req.headers.get("User-Agent") or "").lower()
    device, browser, os_name = detect_device(ua)
    # get country via geo (if available, but we can use ip geo quickly)
    ip = req.remote_addr or "127.0.0.1"
    country = "unknown"
    try:
        # try to get from scans? fallback
        geo = get_geo_from_ip(ip)
        country = geo.get("country", "unknown").lower()
    except Exception:
        pass
    # evaluate rules in order — flexible matching for personal use
    for rule in rules:
        cond = (rule.get("condition") or "").lower().strip()
        url = rule.get("url")
        if not cond or not url:
            continue
        # exact device match
        if cond in ("android", "ios", "mobile", "desktop"):
            # android/ios can be either device or OS
            if cond == "android" and "android" in os_name.lower():
                return url
            if cond == "ios" and "ios" in os_name.lower():
                return url
            if cond == device.lower():
                return url
        if cond.startswith("device:"):
            want = cond.split(":",1)[1].strip().lower()
            if want == device.lower() or (want=="android" and "android" in os_name.lower()) or (want=="ios" and "ios" in os_name.lower()):
                return url
            if want in ua.lower():
                return url
        if cond.startswith("os:"):
            want = cond.split(":",1)[1].strip().lower()
            if want in os_name.lower() or want in ua.lower():
                return url
        if cond.startswith("browser:"):
            want = cond.split(":",1)[1].strip().lower()
            if want in browser.lower() or want in ua.lower():
                return url
        if cond.startswith("country:"):
            want = cond.split(":",1)[1].strip().lower()
            if want == country.lower():
                return url
        if cond.startswith("lang:"):
            lang = cond.split(":",1)[1].strip().lower()
            accept = (req.headers.get("Accept-Language") or "").lower()
            if lang in accept:
                return url
        # direct contains check (e.g., "android" in UA)
        if cond in ua.lower():
            return url
    return primary

def build_qr_content(qr_type, data):
    t = qr_type.lower().strip()
    d = data or {}
    try:
        if t == "url" or t == "link":
            url = d.get("url") or d.get("content") or "https://nareandco.com"
            if not re.match(r'^https?://', url):
                url = "https://" + url
            return url
        elif t == "text":
            return d.get("text") or d.get("content") or "Hello NARE & CO"
        elif t == "email":
            email = d.get("email","")
            subj = d.get("subject","")
            body = d.get("body","")
            return f"mailto:{email}?subject={subj}&body={body}"
        elif t == "sms":
            num = d.get("phone") or d.get("number") or ""
            msg = d.get("message") or d.get("body") or ""
            return f"SMSTO:{num}:{msg}"
        elif t == "wifi":
            ssid = d.get("ssid","")
            pwd = d.get("password","")
            enc = d.get("encryption","WPA")
            hidden = "true" if d.get("hidden") else "false"
            return f"WIFI:T:{enc};S:{ssid};P:{pwd};H:{hidden};;"
        elif t == "vcard":
            fn = d.get("name") or d.get("fullName") or "John Doe"
            org = d.get("organization") or ""
            phone = d.get("phone") or ""
            email = d.get("email") or ""
            url = d.get("url") or ""
            addr = d.get("address") or ""
            return f"BEGIN:VCARD\nVERSION:3.0\nFN:{fn}\nORG:{org}\nTEL:{phone}\nEMAIL:{email}\nURL:{url}\nADR:{addr}\nEND:VCARD"
        elif t == "whatsapp":
            phone = d.get("phone","")
            msg = d.get("message","")
            return f"https://wa.me/{phone}?text={msg}"
        elif t == "location":
            lat = d.get("latitude") or d.get("lat") or "0"
            lon = d.get("longitude") or d.get("lon") or "0"
            return f"geo:{lat},{lon}"
        elif t == "event":
            title = d.get("title","Event")
            loc = d.get("location","")
            start = d.get("start") or d.get("startDate") or "20260101T100000Z"
            end = d.get("end") or d.get("endDate") or "20260101T120000Z"
            desc = d.get("description","")
            return f"BEGIN:VEVENT\nSUMMARY:{title}\nLOCATION:{loc}\nDTSTART:{start}\nDTEND:{end}\nDESCRIPTION:{desc}\nEND:VEVENT"
        elif t in ["facebook","instagram","youtube","tiktok","twitter","pinterest","linkedin"]:
            return d.get("url") or d.get("link") or f"https://{t}.com/"
        elif t == "mp3" or t == "audio":
            return d.get("url") or d.get("link") or ""
        elif t == "file":
            return d.get("url") or d.get("fileUrl") or d.get("content") or "https://nareandco.com/file"
        elif t in ["appstore","app stores"]:
            android = d.get("android") or ""
            ios = d.get("ios") or ""
            return android or ios or "https://play.google.com/store"
        elif t == "smarturl" or t == "smart url" or t=="multiurl":
            # Store rules but return primary for generation; routing happens on redirect
            return d.get("primaryUrl") or d.get("url") or "https://nareandco.com"
        elif t == "gs1":
            return build_gs1_content(d)
        elif t == "menu":
            return d.get("url") or json.dumps(d)
        elif t == "landingpage" or t=="landing page":
            return d.get("url") or "https://nareandco.com/landing"
        elif t == "linkpage" or t=="link page" or t=="bio":
            return d.get("url") or json.dumps(d.get("links",[]))
        elif t == "googlereview" or t=="google review":
            return d.get("url") or ""
        elif t == "googleform":
            return d.get("url") or ""
        else:
            return d.get("url") or d.get("content") or d.get("text") or json.dumps(d)
    except Exception as e:
        logger.warning(f"build_qr_content error for {qr_type}: {e}")
        return str(data)

def detect_device(user_agent):
    ua = (user_agent or "").lower()
    device = "Desktop"
    browser = "Unknown"
    os_name = "Unknown"
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        device = "Mobile"
    elif "tablet" in ua or "ipad" in ua:
        device = "Tablet"
    if "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "edg" in ua:
        browser = "Edge"
    if "windows" in ua:
        os_name = "Windows"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "mac os" in ua:
        os_name = "iOS/Mac"
    elif "linux" in ua:
        os_name = "Linux"
    return device, browser, os_name

def get_geo_from_ip(ip):
    # Real geo via ip-api.com (free, no key) â€” fallback to Unknown
    # Handle private/local IPs
    if not ip or ip in ("127.0.0.1", "::1") or ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
        # Check if 172.16-31
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                if 16 <= second <= 31:
                    return {"country": "Local", "city": "Local"}
            except Exception:
                pass
        if ip.startswith("192.168.") or ip.startswith("10.") or ip in ("127.0.0.1","::1"):
            return {"country": "Local", "city": "Local"}
        # For other private, still try external but likely fail
    # Try external service with timeout
    try:
        # Use ip-api.com with fields filter to reduce payload
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city,status", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                return {"country": data.get("country","Unknown"), "city": data.get("city","Unknown")}
    except Exception as e:
        logger.debug(f"Geo lookup failed for {ip}: {e}")
    # Fallback try ipapi.co (alternative)
    try:
        resp = requests.get(f"https://ipapi.co/{ip}/json/", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            return {"country": data.get("country_name","Unknown"), "city": data.get("city","Unknown")}
    except Exception as e:
        logger.debug(f"Geo fallback failed for {ip}: {e}")
    return {"country": "Unknown", "city": "Unknown"}

def create_qr_image(content, fg_color="#0A0A0A", bg_color="#FFFFFF", pattern="square", eye_style="square", gradient=None, logo_path=None, frame_text=None, frame_color="#00FF88", size=1000, error_correction=qrcode.constants.ERROR_CORRECT_H):
    if pattern == "dots" or pattern == "dot":
        drawer = CircleModuleDrawer()
        eye_drawer = CircleModuleDrawer()
    elif pattern == "rounded":
        drawer = RoundedModuleDrawer()
        eye_drawer = RoundedModuleDrawer()
    elif pattern == "gapped":
        drawer = GappedSquareModuleDrawer()
        eye_drawer = GappedSquareModuleDrawer()
    elif pattern == "extra-rounded":
        drawer = RoundedModuleDrawer(radius_ratio=0.8)
        eye_drawer = RoundedModuleDrawer()
    else:
        drawer = SquareModuleDrawer()
        eye_drawer = SquareModuleDrawer()

    if eye_style == "circle":
        eye_drawer = CircleModuleDrawer()
    elif eye_style == "rounded":
        eye_drawer = RoundedModuleDrawer()
    elif eye_style == "leaf":
        eye_drawer = RoundedModuleDrawer()

    try:
        fg_rgb = hex_to_rgb(fg_color) if fg_color else (10,10,10)
        bg_rgb = hex_to_rgb(bg_color) if bg_color else (255,255,255)
    except Exception as e:
        logger.warning(f"Color parse failed {fg_color}/{bg_color}: {e}")
        fg_rgb=(10,10,10); bg_rgb=(255,255,255)

    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)

    if gradient and gradient != "none" and gradient != "solid":
        try:
            if gradient == "radial":
                color_mask = RadialGradiantColorMask(back_color=bg_rgb, center_color=fg_rgb, edge_color=hex_to_rgb("#00FF88"))
            else:
                color_mask = SquareGradiantColorMask(back_color=bg_rgb, center_color=fg_rgb, edge_color=hex_to_rgb("#00FF88"))
        except Exception as e:
            logger.warning(f"Gradient mask failed: {e}")
            color_mask = SolidFillColorMask(back_color=bg_rgb, front_color=fg_rgb)
    else:
        color_mask = SolidFillColorMask(back_color=bg_rgb, front_color=fg_rgb)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        eye_drawer=eye_drawer,
        color_mask=color_mask
    ).convert("RGBA")

    img = img.resize((size, size), Image.LANCZOS)

    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_size = int(size * 0.22)
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            bg_size = logo_size + 20
            logo_bg = Image.new("RGBA", (bg_size, bg_size), (255,255,255,255))
            mask = Image.new("L", (bg_size, bg_size), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([0,0,bg_size,bg_size], radius=18, fill=255)
            logo_bg.putalpha(mask)
            pos_bg = ((size - bg_size)//2, (size - bg_size)//2)
            img.paste(logo_bg, pos_bg, logo_bg)
            pos = ((size - logo_size)//2, (size - logo_size)//2)
            img.paste(logo, pos, logo)
        except Exception as e:
            logger.warning(f"logo overlay failed: {e}")

    if frame_text:
        try:
            frame_h = int(size * 0.14)
            new_h = size + frame_h
            try:
                fc = hex_to_rgb(frame_color) if frame_color else hex_to_rgb("#00FF88")
            except Exception:
                fc = (0,255,136)
            framed = Image.new("RGBA", (size, new_h), fc + (255,))
            framed.paste(img, (0,0))
            draw = ImageDraw.Draw(framed)
            # Font fallback chain
            font = None
            for fp in ["arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial.ttf", "C:\\Windows\\Fonts\\arial.ttf"]:
                try:
                    font = ImageFont.truetype(fp, size=int(frame_h*0.45))
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()
            text = frame_text[:32]
            bbox = draw.textbbox((0,0), text, font=font)
            tw = bbox[2]-bbox[0]
            th = bbox[3]-bbox[1]
            tx = (size - tw)//2
            ty = size + (frame_h - th)//2 - 4
            brightness = (fc[0]*299 + fc[1]*587 + fc[2]*114)/1000
            text_color = (0,0,0) if brightness>150 else (255,255,255)
            draw.text((tx,ty), text, fill=text_color, font=font)
            img = framed
        except Exception as e:
            logger.warning(f"frame render failed: {e}")

    return img

def create_qr_svg(content, fg_color="#0A0A0A", bg_color="#FFFFFF", size=400):
    # Real SVG generation â€” not PNG masquerading
    # Use SvgPathImage for clean vector
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(content)
    qr.make(fit=True)
    # Generate SVG to BytesIO
    buf = BytesIO()
    # Use factory that supports styling; fallback to basic if styled not available for SVG
    try:
        img = qr.make_image(image_factory=SvgPathImage)
        img.save(buf)
        svg_data = buf.getvalue().decode()
        # Inject colors: replace default black/white
        # SvgPathImage uses fill="#000000" and background white â€” replace
        try:
            # fg
            fg = fg_color if fg_color else "#0A0A0A"
            bg = bg_color if bg_color else "#FFFFFF"
            # Ensure svg has background rect
            if 'background' not in svg_data.lower():
                # Add background via style if missing â€” wrap with rect
                # Simple replace: add style to path
                svg_data = svg_data.replace('fill="#000000"', f'fill="{fg}"')
                svg_data = svg_data.replace('#000000', fg)
                svg_data = svg_data.replace('#000', fg)
            else:
                svg_data = svg_data.replace('#FFFFFF', bg).replace('#ffffff', bg)
                svg_data = svg_data.replace('#000000', fg).replace('#000', fg)
        except Exception as e:
            logger.debug(f"SVG color inject failed: {e}")
        return svg_data
    except Exception as e:
        logger.warning(f"SVG generation failed, fallback: {e}")
        # Fallback: generate PNG and convert? But we state it's SVG, so return minimal SVG with text
        return f'<svg xmlns="http://www.w3.org/2000/svg"><text>{content}</text></svg>'

def image_to_base64(img, fmt="PNG"):
    buf = BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()

# ---------------- Routes: Static ----------------
@app.route("/")
def index():
    fm = os.path.join(APP_DIR, "frontend", "index.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "index.html")
    return send_from_directory(STATIC_DIR, "index.html") if os.path.exists(os.path.join(STATIC_DIR,"index.html")) else "NARE & CO - Frontend not found"

@app.route("/dashboard")
def dashboard_page():
    fm = os.path.join(APP_DIR, "frontend", "dashboard.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "dashboard.html")
    return "Dashboard not found", 404

@app.route("/analytics")
def analytics_page():
    fm = os.path.join(APP_DIR, "frontend", "analytics.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "analytics.html")
    return "Analytics not found", 404

@app.route("/pricing")
def pricing_page():
    fm = os.path.join(APP_DIR, "frontend", "pricing.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "pricing.html")
    return "Pricing not found", 404

@app.route("/api-docs")
def api_docs_page():
    fm = os.path.join(APP_DIR, "frontend", "api-docs.html")
    if os.path.exists(fm):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "api-docs.html")
    return "API docs not found", 404

@app.route("/frontend/<path:path>")
def frontend_static(path):
    return send_from_directory(os.path.join(APP_DIR, "frontend"), path)

# ---------------- API: Auth ----------------
@app.route("/api/register", methods=["POST"])
@rate_limit(limit=5, window=60, key_func=lambda: request.remote_addr or "unknown")
def register():
    data = request.get_json() or {}
    email = data.get("email","").strip().lower()
    password = data.get("password","")
    name = data.get("name","")
    if not email or not password:
        return jsonify({"error":"Email and password required"}), 400
    if not validate_email_format(email):
        return jsonify({"error":"Invalid email format"}), 400
    ok, msg = validate_password_strength(password)
    if not ok:
        return jsonify({"error": msg}), 400
    db = get_db()
    try:
        cur = db.cursor()
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            return jsonify({"error":"Email already registered"}), 409
        pwd_hash = generate_password_hash(password)
        now = datetime.datetime.utcnow().isoformat()
        cur.execute("INSERT INTO users (email,password_hash,name,created_at) VALUES (?,?,?,?)", (email,pwd_hash,name,now))
        db.commit()
        uid = cur.lastrowid
        cur.execute("INSERT INTO folders (user_id,name,created_at) VALUES (?,?,?)", (uid,"My QR Codes",now))
        db.commit()
        token = jwt.encode({"user_id":uid,"email":email,"exp": datetime.datetime.utcnow()+datetime.timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALGO)
        db.close()
        logger.info(f"New user registered: {email}")
        return jsonify({"token":token,"user":{"id":uid,"email":email,"name":name}})
    except Exception as e:
        logger.exception(f"Register error for {email}: {e}")
        try:
            db.close()
        except Exception:
            pass
        return jsonify({"error":"Registration failed"}), 500

@app.route("/api/login", methods=["POST"])
@rate_limit(limit=5, window=60, key_func=lambda: request.remote_addr or "unknown")
def login():
    data = request.get_json() or {}
    email = data.get("email","").strip().lower()
    password = data.get("password","")
    if not email or not password:
        return jsonify({"error":"Email and password required"}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    db.close()
    if not row or not check_password_hash(row["password_hash"], password):
        logger.warning(f"Failed login attempt for {email} from {request.remote_addr}")
        return jsonify({"error":"Invalid credentials"}), 401
    # Check 2FA
    if row["twofa_enabled"]:
        # Don't issue token yet â€” require 2FA step
        temp_token = jwt.encode({"user_id":row["id"],"email":email,"exp": datetime.datetime.utcnow()+datetime.timedelta(minutes=5), "2fa_pending": True}, JWT_SECRET, algorithm=JWT_ALGO)
        return jsonify({"need_2fa": True, "temp_token": temp_token, "message": "2FA required"})
    token = jwt.encode({"user_id":row["id"],"email":email,"exp": datetime.datetime.utcnow()+datetime.timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALGO)
    logger.info(f"User login: {email}")
    return jsonify({"token":token,"user":{"id":row["id"],"email":email,"name":row["name"]}})

@app.route("/api/forgot-password", methods=["POST"])
@rate_limit(limit=3, window=600)
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email","").strip().lower()
    if not email or not validate_email_format(email):
        return jsonify({"error":"Valid email required"}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if not row:
        db.close()
        # Don't reveal if email exists
        return jsonify({"message":"If that email exists, a reset link has been generated. Check server logs (personal use)."}), 200
    # Generate reset token valid 15 min
    reset_token = secrets.token_urlsafe(32)
    expires = (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).isoformat()
    cur.execute("UPDATE users SET reset_token=?, reset_expires=? WHERE email=?", (generate_password_hash(reset_token), expires, email))
    db.commit()
    db.close()
    # For personal use, log token (in real app, email it)
    logger.info(f"Password reset token for {email}: {reset_token} (expires {expires})")
    print(f"[NARE & CO.] Password reset for {email}: token={reset_token} expires {expires}")
    # Return token directly for personal local use (so user can see it)
    return jsonify({"message":"Reset token generated (see server logs).","reset_token": reset_token, "expires": expires}), 200

@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json() or {}
    email = data.get("email","").strip().lower()
    token = data.get("token","")
    new_pwd = data.get("new_password") or data.get("password","")
    if not email or not token or not new_pwd:
        return jsonify({"error":"email, token and new_password required"}), 400
    ok, msg = validate_password_strength(new_pwd)
    if not ok:
        return jsonify({"error": msg}), 400
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT reset_token, reset_expires FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if not row or not row["reset_token"]:
        db.close()
        return jsonify({"error":"Invalid or expired reset token"}), 400
    try:
        exp = datetime.datetime.fromisoformat(row["reset_expires"])
        if datetime.datetime.utcnow() > exp:
            db.close()
            return jsonify({"error":"Reset token expired"}), 400
    except Exception:
        pass
    if not check_password_hash(row["reset_token"], token):
        db.close()
        return jsonify({"error":"Invalid token"}), 400
    cur.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_expires=NULL WHERE email=?", (generate_password_hash(new_pwd), email))
    db.commit()
    db.close()
    logger.info(f"Password reset successful for {email}")
    return jsonify({"message":"Password updated"}), 200

# 2FA endpoints
@app.route("/api/2fa/setup", methods=["POST"])
@token_required
def setup_2fa():
    try:
        import pyotp
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT twofa_secret FROM users WHERE id=?", (g.user_id,))
        row = cur.fetchone()
        secret = row["twofa_secret"] if row and row["twofa_secret"] else pyotp.random_base32()
        if not row or not row["twofa_secret"]:
            cur.execute("UPDATE users SET twofa_secret=? WHERE id=?", (secret, g.user_id))
            db.commit()
        # Generate QR provisioning URI
        user_email = g.user_email
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user_email, issuer_name="NARE & CO.")
        # Also generate QR image for the URI
        qr_img = create_qr_image(uri, size=400)
        b64 = image_to_base64(qr_img)
        db.close()
        return jsonify({"secret": secret, "uri": uri, "qr_base64": f"data:image/png;base64,{b64}"})
    except ImportError:
        return jsonify({"error":"2FA not available (pyotp not installed)"}), 500
    except Exception as e:
        logger.exception(f"2FA setup failed: {e}")
        return jsonify({"error":"2FA setup failed"}), 500

@app.route("/api/2fa/verify-setup", methods=["POST"])
@token_required
def verify_2fa_setup():
    data = request.get_json() or {}
    code = data.get("code","").strip()
    if not code:
        return jsonify({"error":"code required"}), 400
    try:
        import pyotp
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT twofa_secret FROM users WHERE id=?", (g.user_id,))
        row = cur.fetchone()
        if not row or not row["twofa_secret"]:
            db.close()
            return jsonify({"error":"No secret, call /setup first"}), 400
        totp = pyotp.TOTP(row["twofa_secret"])
        if totp.verify(code, valid_window=1):
            cur.execute("UPDATE users SET twofa_enabled=1 WHERE id=?", (g.user_id,))
            db.commit()
            db.close()
            logger.info(f"2FA enabled for user {g.user_id}")
            return jsonify({"message":"2FA enabled"})
        db.close()
        return jsonify({"error":"Invalid code"}), 400
    except Exception as e:
        logger.exception(f"2FA verify failed: {e}")
        return jsonify({"error":"Verify failed"}), 500

@app.route("/api/2fa/disable", methods=["POST"])
@token_required
def disable_2fa():
    data = request.get_json() or {}
    code = data.get("code","")
    # If 2FA enabled, require code to disable
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT twofa_secret, twofa_enabled FROM users WHERE id=?", (g.user_id,))
    row = cur.fetchone()
    if row and row["twofa_enabled"]:
        if not code:
            db.close()
            return jsonify({"error":"code required to disable"}), 400
        try:
            import pyotp
            totp = pyotp.TOTP(row["twofa_secret"])
            if not totp.verify(code, valid_window=1):
                db.close()
                return jsonify({"error":"Invalid code"}), 400
        except Exception as e:
            logger.warning(f"2FA disable verify failed: {e}")
            db.close()
            return jsonify({"error":"Invalid code"}), 400
    cur.execute("UPDATE users SET twofa_enabled=0, twofa_secret=NULL WHERE id=?", (g.user_id,))
    db.commit()
    db.close()
    return jsonify({"message":"2FA disabled"})

@app.route("/api/2fa/login-verify", methods=["POST"])
def login_2fa_verify():
    data = request.get_json() or {}
    temp_token = data.get("temp_token","")
    code = data.get("code","").strip()
    if not temp_token or not code:
        return jsonify({"error":"temp_token and code required"}), 400
    try:
        payload = jwt.decode(temp_token, JWT_SECRET, algorithms=[JWT_ALGO])
        if not payload.get("2fa_pending"):
            return jsonify({"error":"Invalid temp token"}), 400
        uid = payload["user_id"]
        email = payload["email"]
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT twofa_secret FROM users WHERE id=?", (uid,))
        row = cur.fetchone()
        db.close()
        if not row or not row["twofa_secret"]:
            return jsonify({"error":"2FA not set up"}), 400
        import pyotp
        totp = pyotp.TOTP(row["twofa_secret"])
        if totp.verify(code, valid_window=1):
            token = jwt.encode({"user_id":uid,"email":email,"exp": datetime.datetime.utcnow()+datetime.timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALGO)
            return jsonify({"token": token, "user": {"id": uid, "email": email}})
        return jsonify({"error":"Invalid 2FA code"}), 401
    except jwt.ExpiredSignatureError:
        return jsonify({"error":"Temp token expired"}), 401
    except Exception as e:
        logger.warning(f"2FA login verify failed: {e}")
        return jsonify({"error":"Verify failed"}), 401

@app.route("/api/me", methods=["GET"])
@token_required
def me():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id,email,name,created_at,is_premium,twofa_enabled FROM users WHERE id=?", (g.user_id,))
    row = cur.fetchone()
    db.close()
    if not row:
        return jsonify({"error":"User not found"}), 404
    return jsonify(dict(row))

# --------------- API: Generate ---------------
@app.route("/api/generate", methods=["POST"])
@rate_limit(limit=20, window=60)
def generate():
    if request.content_type and "multipart/form-data" in request.content_type:
        qr_type = request.form.get("type","url")
        data_json = request.form.get("data","{}")
        try:
            data = json.loads(data_json)
        except Exception:
            data = {"url": data_json}
        is_dynamic = request.form.get("is_dynamic")=="true"
        fg_color = request.form.get("fg_color","#0A0A0A")
        bg_color = request.form.get("bg_color","#FFFFFF")
        pattern = request.form.get("pattern","square")
        eye_style = request.form.get("eye_style","square")
        frame_text = request.form.get("frame_text","")
        frame_color = request.form.get("frame_color","#00FF88")
        gradient = request.form.get("gradient","solid")
        name = request.form.get("name","My QR")
        logo_file = request.files.get("logo")
    else:
        body = request.get_json() or {}
        qr_type = body.get("type","url")
        data = body.get("data",{})
        if isinstance(data, str):
            data = {"content": data}
        is_dynamic = body.get("is_dynamic", False)
        fg_color = body.get("fg_color","#0A0A0A")
        bg_color = body.get("bg_color","#FFFFFF")
        pattern = body.get("pattern","square")
        eye_style = body.get("eye_style","square")
        frame_text = body.get("frame_text","")
        frame_color = body.get("frame_color","#00FF88")
        gradient = body.get("gradient","solid")
        name = body.get("name","My QR")
        logo_file = None
        logo_b64 = body.get("logo_base64")
        if logo_b64:
            try:
                header, b64data = logo_b64.split(",",1) if "," in logo_b64 else ("", logo_b64)
                img_data = base64.b64decode(b64data)
                # Validate MIME? Check size already limited by MAX_CONTENT_LENGTH
                tmp_path = os.path.join(UPLOAD_DIR, f"tmp_{secrets.token_hex(4)}.png")
                with open(tmp_path,"wb") as f:
                    f.write(img_data)
                # Validate via PIL
                try:
                    im = Image.open(tmp_path)
                    im.verify()
                    if im.format not in ("PNG","JPEG","JPG","WEBP","SVG"):
                        logger.warning(f"Logo format not allowed: {im.format}")
                except Exception as e:
                    logger.warning(f"Logo validation failed: {e}")
                    os.remove(tmp_path)
                    raise
                logo_path_tmp = tmp_path
            except Exception as e:
                logger.warning(f"Logo b64 processing failed: {e}")
                logo_path_tmp = None
        else:
            logo_path_tmp = None

    logo_path = None
    if 'logo_file' in locals() and logo_file:
        # MIME whitelist
        allowed_ext = {".png",".jpg",".jpeg",".webp",".svg"}
        ext = os.path.splitext(secure_filename(logo_file.filename or "logo.png"))[1].lower()
        if ext not in allowed_ext:
            return jsonify({"error": f"Logo type not allowed: {ext}"}), 400
        fname = secure_filename(logo_file.filename or "logo.png")
        tmp_name = f"{secrets.token_hex(6)}_{fname}"
        logo_path = os.path.join(UPLOAD_DIR, tmp_name)
        logo_file.save(logo_path)
        # Validate via PIL
        try:
            im = Image.open(logo_path)
            im.verify()
        except Exception as e:
            try:
                os.remove(logo_path)
            except Exception:
                pass
            logger.warning(f"Logo file validation failed: {e}")
            return jsonify({"error":"Invalid image file"}), 400
    elif 'logo_path_tmp' in locals() and logo_path_tmp and os.path.exists(logo_path_tmp):
        logo_path = logo_path_tmp

    content = build_qr_content(qr_type, data)

    user_id = optional_auth()
    short_code = None
    final_content = content
    if is_dynamic:
        # Generate with proper entropy and uniqueness check
        db_tmp = get_db()
        for _ in range(10):
            cand = generate_short_code(8)
            try:
                cur = db_tmp.cursor()
                cur.execute("SELECT id FROM qrcodes WHERE short_code=?", (cand,))
                if not cur.fetchone():
                    short_code = cand
                    break
            except Exception as e:
                logger.warning(f"short_code check failed: {e}")
                break
        db_tmp.close()
        if not short_code:
            short_code = generate_short_code(8)
        final_content = f"{get_base_url(request)}/r/{short_code}"

    password = None
    scan_limit = None
    expiry_date = None
    if request.is_json:
        body2 = request.get_json() or {}
        password = body2.get("password")
        scan_limit = body2.get("scan_limit")
        expiry_date = body2.get("expiry_date")
    else:
        password = request.form.get("password")
        scan_limit = request.form.get("scan_limit")
        expiry_date = request.form.get("expiry_date")

    # Validate scan_limit
    if scan_limit is not None:
        try:
            scan_limit = int(scan_limit)
            if scan_limit <= 0:
                scan_limit = None
        except Exception:
            scan_limit = None

    pwd_hash = generate_password_hash(password) if password else None

    try:
        img = create_qr_image(
            content=final_content,
            fg_color=fg_color,
            bg_color=bg_color,
            pattern=pattern,
            eye_style=eye_style,
            gradient=gradient,
            logo_path=logo_path,
            frame_text=frame_text,
            frame_color=frame_color,
            size=900
        )
        b64 = image_to_base64(img, "PNG")
        qr_id = None
        if user_id:
            db = get_db()
            cur = db.cursor()
            now = datetime.datetime.utcnow().isoformat()
            # Use transaction with try for UNIQUE violation
            try:
                cur.execute("""INSERT INTO qrcodes
                (user_id,folder_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,gradient,pattern,eye_style,frame_text,frame_color,logo_path,has_password,password_hash,expiry_date,scan_limit,scan_count,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, None, name, qr_type, content, json.dumps(data), 1 if is_dynamic else 0, short_code, fg_color, bg_color, gradient, pattern, eye_style, frame_text, frame_color, logo_path, 1 if pwd_hash else 0, pwd_hash, expiry_date, scan_limit, 0, now, now)
                )
                db.commit()
                qr_id = cur.lastrowid
            except sqlite3.IntegrityError as e:
                db.rollback()
                logger.warning(f"Short code collision, retry: {e}")
                # Retry once with new code if dynamic
                if is_dynamic:
                    short_code = generate_short_code(8)
                    final_content = f"{get_base_url(request)}/r/{short_code}"
                    # Regenerate image with new URL
                    img = create_qr_image(final_content, fg_color, bg_color, pattern, eye_style, gradient, logo_path, frame_text, frame_color, size=900)
                    b64 = image_to_base64(img, "PNG")
                    cur.execute("""INSERT INTO qrcodes
                    (user_id,folder_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,gradient,pattern,eye_style,frame_text,frame_color,logo_path,has_password,password_hash,expiry_date,scan_limit,scan_count,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (user_id, None, name, qr_type, content, json.dumps(data), 1 if is_dynamic else 0, short_code, fg_color, bg_color, gradient, pattern, eye_style, frame_text, frame_color, logo_path, 1 if pwd_hash else 0, pwd_hash, expiry_date, scan_limit, 0, now, now)
                    )
                    db.commit()
                    qr_id = cur.lastrowid
                else:
                    raise
            finally:
                db.close()
        return jsonify({
            "success": True,
            "content": final_content,
            "original_content": content,
            "image_base64": f"data:image/png;base64,{b64}",
            "short_code": short_code,
            "qr_id": qr_id,
            "is_dynamic": is_dynamic,
            "type": qr_type
        })
    except Exception as e:
        logger.exception(f"Generate failed: {e}")
        return jsonify({"error": "Generation failed"}), 500

@app.route("/api/preview", methods=["POST"])
def preview():
    body = request.get_json() or {}
    content = body.get("content") or build_qr_content(body.get("type","url"), body.get("data",{}))
    if not content:
        return jsonify({"error":"Content required"}), 400
    fg = body.get("fg_color","#0A0A0A")
    bg = body.get("bg_color","#FFFFFF")
    pat = body.get("pattern","square")
    eye = body.get("eye_style","square")
    grad = body.get("gradient","solid")
    frame = body.get("frame_text","")
    fcol = body.get("frame_color","#00FF88")
    logo_b64 = body.get("logo_base64")
    logo_path = None
    if logo_b64:
        try:
            h, d = logo_b64.split(",",1) if "," in logo_b64 else ("", logo_b64)
            img_data = base64.b64decode(d)
            if len(img_data) > 5*1024*1024:
                return jsonify({"error":"Logo too large"}), 400
            tmp = os.path.join(UPLOAD_DIR, f"prev_{secrets.token_hex(4)}.png")
            with open(tmp,"wb") as f:
                f.write(img_data)
            # Validate
            try:
                im = Image.open(tmp)
                im.verify()
            except Exception as e:
                logger.warning(f"Preview logo invalid: {e}")
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                return jsonify({"error":"Invalid logo image"}), 400
            logo_path = tmp
        except Exception as e:
            logger.warning(f"Preview logo decode failed: {e}")
            return jsonify({"error":"Invalid logo"}), 400
    try:
        img = create_qr_image(content, fg, bg, pat, eye, grad, logo_path, frame, fcol, size=800)
        b64 = image_to_base64(img)
        return jsonify({"image_base64": f"data:image/png;base64,{b64}"})
    except Exception as e:
        logger.exception(f"Preview failed: {e}")
        return jsonify({"error":"Preview failed"}), 500

@app.route("/api/qrcodes", methods=["GET"])
@token_required
def list_qrcodes():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE user_id=? ORDER BY created_at DESC", (g.user_id,))
    rows = cur.fetchall()
    db.close()
    out=[]
    for r in rows:
        d=dict(r)
        d.pop("password_hash",None)
        # Don't expose absolute logo_path; give relative if needed
        if d.get("logo_path"):
            d["has_logo"] = True
        out.append(d)
    return jsonify(out)

@app.route("/api/qrcodes/<int:qr_id>", methods=["GET"])
@token_required
def get_qrcode(qr_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id, g.user_id))
    row=cur.fetchone()
    db.close()
    if not row:
        return jsonify({"error":"Not found"}),404
    d=dict(row)
    d.pop("password_hash",None)
    return jsonify(d)

@app.route("/api/qrcodes/<int:qr_id>", methods=["PUT"])
@token_required
def update_qrcode(qr_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id, g.user_id))
    row=cur.fetchone()
    if not row:
        db.close()
        return jsonify({"error":"Not found"}),404
    body=request.get_json() or {}
    fields=[]
    vals=[]
    for f in ["name","type","content","data_json","fg_color","bg_color","gradient","pattern","eye_style","frame_text","frame_color","folder_id"]:
        if f in body:
            fields.append(f"{f}=?")
            vals.append(body[f] if f!="data_json" or isinstance(body[f], str) else json.dumps(body[f]))
    # Validate colors if provided
    for col in ["fg_color","bg_color","frame_color"]:
        if col in body and body[col]:
            if not re.match(r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$", body[col]):
                db.close()
                return jsonify({"error": f"Invalid color {col}"}), 400
    if "password" in body:
        if body["password"]:
            if len(body["password"]) < 4:
                db.close()
                return jsonify({"error":"Password too short"}), 400
            fields.append("has_password=1")
            fields.append("password_hash=?")
            vals.append(generate_password_hash(body["password"]))
        else:
            fields.append("has_password=0")
            fields.append("password_hash=NULL")
    if "expiry_date" in body:
        fields.append("expiry_date=?"); vals.append(body["expiry_date"])
    if "scan_limit" in body:
        # validate
        try:
            sl = int(body["scan_limit"]) if body["scan_limit"] is not None else None
            if sl is not None and sl <= 0:
                raise ValueError
            fields.append("scan_limit=?"); vals.append(sl)
        except Exception:
            db.close()
            return jsonify({"error":"Invalid scan_limit"}), 400
    if "data" in body:
        new_content = build_qr_content(body.get("type", row["type"]), body["data"])
        fields.append("content=?"); vals.append(new_content)
        fields.append("data_json=?"); vals.append(json.dumps(body["data"]))
    if fields:
        fields.append("updated_at=?"); vals.append(datetime.datetime.utcnow().isoformat())
        vals.append(qr_id); vals.append(g.user_id)
        sql = f"UPDATE qrcodes SET {', '.join(fields)} WHERE id=? AND user_id=?"
        try:
            cur.execute(sql, vals)
            db.commit()
        except Exception as e:
            logger.exception(f"Update failed for {qr_id}: {e}")
            db.close()
            return jsonify({"error":"Update failed"}), 500
    cur.execute("SELECT * FROM qrcodes WHERE id=?", (qr_id,))
    updated=dict(cur.fetchone())
    updated.pop("password_hash",None)
    db.close()
    return jsonify(updated)

@app.route("/api/qrcodes/<int:qr_id>", methods=["DELETE"])
@token_required
def delete_qrcode(qr_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT scan_count FROM qrcodes WHERE id=? AND user_id=?", (qr_id, g.user_id))
    row=cur.fetchone()
    if not row:
        db.close()
        return jsonify({"error":"Not found"}),404
    try:
        cur.execute("DELETE FROM qrcodes WHERE id=? AND user_id=?", (qr_id, g.user_id))
        cur.execute("DELETE FROM scans WHERE qr_id=?", (qr_id,))
        db.commit()
        logger.info(f"QR {qr_id} deleted by user {g.user_id}")
    except Exception as e:
        logger.exception(f"Delete failed: {e}")
        db.close()
        return jsonify({"error":"Delete failed"}), 500
    db.close()
    return jsonify({"success":True})

@app.route("/api/qrcodes/bulk", methods=["POST"])
@token_required
def bulk_generate():
    if "file" not in request.files:
        return jsonify({"error":"CSV file required"}),400
    file=request.files["file"]
    typ=request.form.get("type","url")
    fg=request.form.get("fg_color","#0A0A0A")
    bg=request.form.get("bg_color","#FFFFFF")
    try:
        data=file.read().decode('utf-8')
        lines=[l.strip() for l in data.splitlines() if l.strip()]
        header=lines[0].lower() if lines else ""
        start=1 if "url" in header or "name" in header else 0
        created=[]
        db=get_db()
        cur=db.cursor()
        for line in lines[start:]:
            parts=[p.strip() for p in line.split(",")]
            url=parts[0] if parts else ""
            name=parts[1] if len(parts)>1 else f"Bulk {secrets.token_hex(2)}"
            if not url:
                continue
            content=build_qr_content(typ, {"url":url})
            # Generate unique short_code with retry
            short = None
            for _ in range(5):
                cand = generate_short_code(8)
                cur.execute("SELECT id FROM qrcodes WHERE short_code=?", (cand,))
                if not cur.fetchone():
                    short = cand
                    break
            if not short:
                short = generate_short_code(8)
            final=f"{get_base_url(request)}/r/{short}"
            now=datetime.datetime.utcnow().isoformat()
            try:
                cur.execute("INSERT INTO qrcodes (user_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,pattern,eye_style,scan_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (g.user_id,name,typ,content, json.dumps({"url":url}), 1, short, fg,bg,"square","square",0,now,now))
                # Commit per row to avoid losing batch on collision
                db.commit()
                created.append({"name":name,"url":url,"short_code":short,"qr_url":final})
            except sqlite3.IntegrityError as e:
                db.rollback()
                logger.warning(f"Bulk insert collision for {url}: {e}")
                continue
            except Exception as e:
                db.rollback()
                logger.warning(f"Bulk insert failed for {url}: {e}")
                continue
            if len(created)>=3000:
                break
        db.close()
        logger.info(f"Bulk generated {len(created)} for user {g.user_id}")
        return jsonify({"created":created, "count":len(created)})
    except Exception as e:
        logger.exception(f"Bulk failed: {e}")
        return jsonify({"error":"Bulk failed"}),500

@app.route("/api/folders", methods=["GET","POST"])
@token_required
def folders():
    db=get_db()
    cur=db.cursor()
    if request.method=="POST":
        body=request.get_json() or {}
        name=body.get("name","New Folder")
        if not name or len(name) > 60:
            db.close()
            return jsonify({"error":"Invalid folder name"}), 400
        now=datetime.datetime.utcnow().isoformat()
        cur.execute("INSERT INTO folders (user_id,name,created_at) VALUES (?,?,?)", (g.user_id,name,now))
        db.commit()
        fid=cur.lastrowid
        db.close()
        return jsonify({"id":fid,"name":name})
    else:
        cur.execute("SELECT * FROM folders WHERE user_id=?", (g.user_id,))
        rows=[dict(r) for r in cur.fetchall()]
        db.close()
        return jsonify(rows)

@app.route("/api/templates", methods=["GET","POST"])
@token_required
def templates():
    db=get_db()
    cur=db.cursor()
    if request.method=="POST":
        body=request.get_json() or {}
        name=body.get("name","Template")
        config=body.get("config",{})
        if len(json.dumps(config)) > 10000:
            db.close()
            return jsonify({"error":"Config too large"}), 400
        now=datetime.datetime.utcnow().isoformat()
        cur.execute("INSERT INTO templates (user_id,name,config_json,created_at) VALUES (?,?,?,?)", (g.user_id,name,json.dumps(config),now))
        db.commit()
        tid=cur.lastrowid
        db.close()
        return jsonify({"id":tid,"name":name})
    else:
        cur.execute("SELECT * FROM templates WHERE user_id=?", (g.user_id,))
        rows=[dict(r) for r in cur.fetchall()]
        db.close()
        return jsonify(rows)

@app.route("/api/analytics/overview", methods=["GET"])
@token_required
def analytics_overview():
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT COUNT(*) as total, SUM(scan_count) as scans FROM qrcodes WHERE user_id=?", (g.user_id,))
    row=cur.fetchone()
    total=row["total"] or 0
    scans=row["scans"] or 0
    cur.execute("SELECT date(timestamp) as d, COUNT(*) as c FROM scans WHERE qr_id IN (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY date(timestamp) ORDER BY d DESC LIMIT 14", (g.user_id,))
    timeline=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT device, COUNT(*) as c FROM scans WHERE qr_id IN (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY device", (g.user_id,))
    devices=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT country, COUNT(*) as c FROM scans WHERE qr_id IN (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY country", (g.user_id,))
    countries=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT id,name,type,scan_count FROM qrcodes WHERE user_id=? ORDER BY scan_count DESC LIMIT 10", (g.user_id,))
    top=[dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify({"total_qrs":total,"total_scans":scans,"timeline":timeline,"devices":devices,"countries":countries,"top":top})

@app.route("/api/qrcodes/<int:qr_id>/analytics", methods=["GET"])
@token_required
def qr_analytics(qr_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id,g.user_id))
    qr=cur.fetchone()
    if not qr:
        db.close()
        return jsonify({"error":"Not found"}),404
    cur.execute("SELECT * FROM scans WHERE qr_id=? ORDER BY timestamp DESC LIMIT 100", (qr_id,))
    scans=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT device, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY device", (qr_id,))
    devices=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT country, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY country", (qr_id,))
    countries=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT date(timestamp) as d, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY date(timestamp) ORDER BY d", (qr_id,))
    timeline=[dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify({"qr":dict(qr),"scans":scans,"devices":devices,"countries":countries,"timeline":timeline})

@app.route("/r/<code>", methods=["GET", "POST"])
def redirect_dynamic(code):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE short_code=?", (code,))
    row=cur.fetchone()
    if not row:
        db.close()
        return "QR not found or expired",404
    if row["expiry_date"]:
        try:
            exp=datetime.datetime.fromisoformat(row["expiry_date"])
            if datetime.datetime.utcnow()>exp:
                db.close()
                return "This QR has expired",410
        except Exception as e:
            logger.warning(f"Expiry parse failed: {e}")
    if row["scan_limit"] and row["scan_count"]>=row["scan_limit"]:
        db.close()
        return "Scan limit reached",410
    # Password check â€” POST only to avoid URL leak
    if row["has_password"]:
        pwd = None
        if request.method == "POST":
            pwd = request.form.get("pwd") or request.form.get("password")
        # Also check Authorization header as alternative (for API)
        if not pwd:
            auth_pwd = request.headers.get("X-QR-Password")
            if auth_pwd:
                pwd = auth_pwd
        if not pwd or not check_password_hash(row["password_hash"], pwd):
            if request.method == "POST":
                # Wrong password â€” show form with error
                db.close()
                return f"""
                <html style="font-family:Inter,sans-serif;background:#0A0A0A;color:white;display:flex;align-items:center;justify-content:center;min-height:100vh">
                <div style="background:#111;border:1px solid #222;padding:40px;border-radius:24px;max-width:400px;width:100%;text-align:center">
                <h2 style="color:#00FF88">ðŸ”’ Password Protected</h2>
                <p>This QR is protected by <b>NARE & CO.</b></p>
                <p style="color:#FF5555;font-size:13px;margin-top:8px">Incorrect password â€” try again</p>
                <form method="POST">
                  <input name="pwd" type="password" placeholder="Enter password" required style="width:100%;padding:14px;border-radius:12px;border:1px solid #333;background:#000;color:white;margin:16px 0"/>
                  <button type="submit" style="width:100%;padding:14px;background:#00FF88;color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer">Unlock</button>
                </form>
                <p style="font-size:12px;color:#888;margin-top:12px">Secured by NARE & CO. â€¢ Grid White / Black / Neon Green</p>
                </div></html>
                """,401
            db.close()
            return f"""
            <html style="font-family:Inter,sans-serif;background:#0A0A0A;color:white;display:flex;align-items:center;justify-content:center;min-height:100vh">
            <div style="background:#111;border:1px solid #222;padding:40px;border-radius:24px;max-width:400px;width:100%;text-align:center">
            <h2 style="color:#00FF88">ðŸ”’ Password Protected</h2>
            <p>This QR is protected by <b>NARE & CO.</b></p>
            <form method="POST">
              <input name="pwd" type="password" placeholder="Enter password" required style="width:100%;padding:14px;border-radius:12px;border:1px solid #333;background:#000;color:white;margin:16px 0"/>
              <button type="submit" style="width:100%;padding:14px;background:#00FF88;color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer">Unlock</button>
            </form>
            <p style="font-size:12px;color:#888;margin-top:12px">Secured by NARE & CO. â€¢ Grid White / Black / Neon Green â€¢ POST only, not logged in URL</p>
            </div></html>
            """,401
    # Track scan â€” real geo!
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
    ua=request.headers.get("User-Agent","")
    device,browser,os_name=detect_device(ua)
    now=datetime.datetime.utcnow().isoformat()
    geo = get_geo_from_ip(ip)
    country = geo.get("country","Unknown")
    city = geo.get("city","Unknown")
    try:
        cur.execute("INSERT INTO scans (qr_id,timestamp,ip,user_agent,device,browser,os,country,city) VALUES (?,?,?,?,?,?,?,?,?)",
                    (row["id"],now,ip,ua,device,browser,os_name,country,city))
        cur.execute("UPDATE qrcodes SET scan_count=scan_count+1, updated_at=? WHERE id=?", (now,row["id"]))
        db.commit()
    except Exception as e:
        logger.exception(f"Scan track failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    # Resolve smart URL if applicable
    target = row["content"]
    if row["type"] in ("smarturl","smart url","multiurl") and row["is_dynamic"]:
        try:
            smarter = resolve_smart_url(row, request)
            if smarter and smarter != target:
                target = smarter
                logger.info(f"Smart URL resolved for {code} -> {target} (device={device} country={country})")
        except Exception as e:
            logger.warning(f"Smart resolve failed: {e}")
    db.close()
    if target.startswith("http"):
        return redirect(target, code=302)
    else:
        return f"""
        <html style="font-family:Inter,sans-serif;background:#F8F9FA;min-height:100vh"><body style="margin:0;padding:40px;background:
        radial-gradient(circle at 1px 1px, #e5e7eb 1px, transparent 0);background-size:22px 22px">
        <div style="max-width:640px;margin:0 auto;background:white;border:1px solid #0A0A0A;border-radius:20px;overflow:hidden;box-shadow:8px 8px 0 #0A0A0A">
        <div style="background:#0A0A0A;color:#00FF88;padding:16px 24px;display:flex;justify-content:space-between;align-items:center"><b>NARE & CO.</b><span style="font-size:12px;border:1px solid #00FF88;padding:4px 8px;border-radius:20px">SECURE QR</span></div>
        <div style="padding:32px"><h2>QR Content</h2><pre style="white-space:pre-wrap;background:#F8F9FA;padding:16px;border-radius:12px;border:1px solid #e5e7eb">{target[:2000]}</pre>
        <p style="color:#666;font-size:13px">Scanned via NARE & CO. dynamic QR â€¢ {device} â€¢ {browser} â€¢ {country}</p></div></div></body></html>
        """

@app.route("/api/download/<int:qr_id>")
@token_required
def download_qr(qr_id):
    fmt=request.args.get("format","png").lower()
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id,g.user_id))
    row=cur.fetchone()
    db.close()
    if not row:
        return jsonify({"error":"Not found"}),404
    if row["is_dynamic"]:
        content=f"{get_base_url(request)}/r/{row['short_code']}"
    else:
        content=row["content"]
    if fmt=="svg":
        # Real SVG
        try:
            svg_text = create_qr_svg(content, row["fg_color"], row["bg_color"])
            buf = BytesIO(svg_text.encode())
            return send_file(buf, mimetype="image/svg+xml", as_attachment=True, download_name=f"nare-co-{qr_id}.svg")
        except Exception as e:
            logger.exception(f"SVG download failed: {e}")
            return jsonify({"error":"SVG generation failed"}), 500
    elif fmt=="pdf":
        # Use top-level imported reportlab
        try:
            img=create_qr_image(content, row["fg_color"], row["bg_color"], row["pattern"], row["eye_style"], row["gradient"], row["logo_path"], row["frame_text"], row["frame_color"], size=1200)
            pdf_buf=BytesIO()
            c=canvas.Canvas(pdf_buf, pagesize=A4)
            w,h=A4
            c.setFillColorRGB(0.04,0.04,0.04)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(40, h-60, "NARE & CO. \u2014 QR Code")
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(0.5,0.5,0.5)
            c.drawString(40, h-75, f"Type: {row['type']} \u2022 {row['name']} \u2022 Generated {row['created_at'][:10]}")
            img_buf=BytesIO()
            img.save(img_buf, format="PNG")
            img_buf.seek(0)
            ir=ImageReader(img_buf)
            c.drawImage(ir, 120, h-500, width=350, height=350, preserveAspectRatio=True, mask='auto')
            c.setFillColorRGB(0,1,0.53)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(w/2, h-520, row["frame_text"] or "Scan Me \u2014 NARE & CO.")
            c.showPage()
            c.save()
            pdf_buf.seek(0)
            return send_file(pdf_buf, mimetype="application/pdf", as_attachment=True, download_name=f"nare-co-{qr_id}.pdf")
        except Exception as e:
            logger.exception(f"PDF generation failed: {e}")
            return jsonify({"error":"PDF failed"}), 500
    else:
        try:
            img=create_qr_image(content, row["fg_color"], row["bg_color"], row["pattern"], row["eye_style"], row["gradient"], row["logo_path"], row["frame_text"], row["frame_color"], size=1200)
            buf=BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return send_file(buf, mimetype="image/png", as_attachment=True, download_name=f"nare-co-{qr_id}.png")
        except Exception as e:
            logger.exception(f"PNG download failed: {e}")
            return jsonify({"error":"PNG failed"}), 500

@app.route("/api/qrcodes/<int:qr_id>/duplicate", methods=["POST"])
@token_required
def duplicate(qr_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id,g.user_id))
    row=cur.fetchone()
    if not row:
        db.close(); return jsonify({"error":"Not found"}),404
    # Generate unique code for duplicate if dynamic
    new_code=None
    if row["is_dynamic"]:
        for _ in range(5):
            cand = generate_short_code(8)
            cur.execute("SELECT id FROM qrcodes WHERE short_code=?", (cand,))
            if not cur.fetchone():
                new_code = cand
                break
        if not new_code:
            new_code = generate_short_code(8)
    now=datetime.datetime.utcnow().isoformat()
    try:
        cur.execute("""INSERT INTO qrcodes
        (user_id,folder_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,gradient,pattern,eye_style,frame_text,frame_color,logo_path,has_password,password_hash,expiry_date,scan_limit,scan_count,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (g.user_id, row["folder_id"], row["name"]+" (Copy)", row["type"], row["content"], row["data_json"], row["is_dynamic"], new_code, row["fg_color"], row["bg_color"], row["gradient"], row["pattern"], row["eye_style"], row["frame_text"], row["frame_color"], row["logo_path"], row["has_password"], row["password_hash"], row["expiry_date"], row["scan_limit"], 0, now, now))
        db.commit()
        nid=cur.lastrowid
    except Exception as e:
        logger.exception(f"Duplicate failed: {e}")
        db.close()
        return jsonify({"error":"Duplicate failed"}), 500
    db.close()
    return jsonify({"id":nid})

# Health
@app.route("/api/health")
def health():
    return jsonify({"status":"ok","service":"NARE & CO.","version":"1.1.0","theme":"grid-white / black / neon-green"})

# Catch-all for frontend routes â€” safe
@app.route("/<path:path>")
def catch_all(path):
    # Safe join: ensure path stays within frontend
    try:
        frontend_abs = os.path.abspath(os.path.join(APP_DIR, "frontend"))
        requested = os.path.abspath(os.path.join(frontend_abs, path))
        # Block traversal
        if not requested.startswith(frontend_abs + os.sep) and requested != frontend_abs:
            logger.warning(f"Blocked traversal attempt: {path}")
            abort(404)
        if os.path.isfile(requested):
            # Use send_from_directory which handles safe serving
            return send_from_directory(frontend_abs, os.path.relpath(requested, frontend_abs))
    except Exception as e:
        logger.warning(f"Catch-all error for {path}: {e}")
    # fallback to index for SPA
    idx = os.path.join(APP_DIR, "frontend", "index.html")
    if os.path.exists(idx):
        return send_from_directory(os.path.join(APP_DIR, "frontend"), "index.html")
    return "Not found", 404

if __name__=="__main__":
    print("=== NARE & CO. â€” Personal Edition ===")
    print("Grid White / Black / Neon Green")
    print(f"Base URL: {get_base_url()}")
    print(f"Allowed Origins: {ALLOWED_ORIGINS}")
    if FLASK_DEBUG:
        print("[WARN] DEBUG mode is ON â€” do not use on public network!")
    print(f"Server: http://{HOST}:{PORT}")
    print("API docs: http://localhost:5000/api-docs")
    # Bind: debug only if env says so, and host is restricted to 127.0.0.1 unless explicitly set
    app.run(host=HOST, port=PORT, debug=FLASK_DEBUG)




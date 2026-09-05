import os
import re
import json
import base64
import sqlite3
import hashlib
import secrets
import datetime
from io import BytesIO
from functools import wraps

import jwt
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer, CircleModuleDrawer, GappedSquareModuleDrawer, RoundedModuleDrawer
)
from qrcode.image.styles.colormasks import SolidFillColorMask, RadialGradiantColorMask, SquareGradiantColorMask
from PIL import Image, ImageDraw, ImageFont, ImageOps
from flask import Flask, request, jsonify, send_from_directory, g, redirect, send_file
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "data", "nare.db")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
STATIC_DIR = os.path.join(APP_DIR, "static")
FRONTEND_DIR = os.path.join(APP_DIR, "frontend")

os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

SECRET_KEY = "nare-co-secret-2026-neon-green-grid-white-black-super-secure-key"
JWT_SECRET = SECRET_KEY
JWT_ALGO = "HS256"

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = UPLOAD_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app, supports_credentials=True)

# ---------------- DB ----------------
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
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
        twofa_secret TEXT
    )""")
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
    db.close()

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
        except Exception as e:
            return jsonify({"error":"Invalid token", "details":str(e)}), 401
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
        except:
            return None
    return None

def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h)==3:
        h=''.join([c*2 for c in h])
    return tuple(int(h[i:i+2],16) for i in (0,2,4))

def generate_short_code(n=7):
    return secrets.token_urlsafe(n)[:n].replace('-','a').replace('_','b')

def build_qr_content(qr_type, data):
    """Map QR type to string content"""
    t = qr_type.lower()
    d = data
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
            # vCard 3.0
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
            # Smart will be handled as dynamic with multiple URLs; for now return primary
            return d.get("primaryUrl") or d.get("url") or "https://nareandco.com"
        elif t == "gs1":
            return d.get("content") or d.get("gtin") or "(01)09506000134352(17)240105(10)ABC123"
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

def create_qr_image(content, fg_color="#0A0A0A", bg_color="#FFFFFF", pattern="square", eye_style="square", gradient=None, logo_path=None, frame_text=None, frame_color="#00FF88", size=1000, error_correction=qrcode.constants.ERROR_CORRECT_H):
    # Select module drawer
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
    # Colors
    try:
        fg_rgb = hex_to_rgb(fg_color) if fg_color else (10,10,10)
        bg_rgb = hex_to_rgb(bg_color) if bg_color else (255,255,255)
    except:
        fg_rgb=(10,10,10); bg_rgb=(255,255,255)

    qr = qrcode.QRCode(
        version=None,
        error_correction=error_correction,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)

    # Color mask
    if gradient and gradient != "none" and gradient != "solid":
        # Use gradient mask with fg -> neon green
        try:
            if gradient == "radial":
                color_mask = RadialGradiantColorMask(back_color=bg_rgb, center_color=fg_rgb, edge_color=hex_to_rgb("#00FF88"))
            else:
                color_mask = SquareGradiantColorMask(back_color=bg_rgb, center_color=fg_rgb, edge_color=hex_to_rgb("#00FF88"))
        except:
            color_mask = SolidFillColorMask(back_color=bg_rgb, front_color=fg_rgb)
    else:
        color_mask = SolidFillColorMask(back_color=bg_rgb, front_color=fg_rgb)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        eye_drawer=eye_drawer,
        color_mask=color_mask
    ).convert("RGBA")

    # Resize to size
    img = img.resize((size, size), Image.LANCZOS)

    # Add logo if exists
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            # Logo size 20-25% of QR
            logo_size = int(size * 0.22)
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            # Add white rounded background behind logo for better scan
            bg_size = logo_size + 20
            logo_bg = Image.new("RGBA", (bg_size, bg_size), (255,255,255,255))
            # rounded rect
            mask = Image.new("L", (bg_size, bg_size), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([0,0,bg_size,bg_size], radius=18, fill=255)
            logo_bg.putalpha(mask)
            # paste bg centered
            pos_bg = ((size - bg_size)//2, (size - bg_size)//2)
            img.paste(logo_bg, pos_bg, logo_bg)
            # paste logo centered
            pos = ((size - logo_size)//2, (size - logo_size)//2)
            img.paste(logo, pos, logo)
        except Exception as e:
            print("logo error", e)

    # Add frame if requested
    if frame_text:
        try:
            frame_h = int(size * 0.14)
            new_h = size + frame_h
            # frame color from param
            try:
                fc = hex_to_rgb(frame_color) if frame_color else hex_to_rgb("#00FF88")
            except:
                fc = (0,255,136)
            framed = Image.new("RGBA", (size, new_h), fc + (255,))
            framed.paste(img, (0,0))
            draw = ImageDraw.Draw(framed)
            # try load font
            try:
                # attempt to load arial
                font = ImageFont.truetype("arial.ttf", size=int(frame_h*0.45))
            except:
                font = ImageFont.load_default()
            text = frame_text[:32]
            # center text
            bbox = draw.textbbox((0,0), text, font=font)
            tw = bbox[2]-bbox[0]
            th = bbox[3]-bbox[1]
            tx = (size - tw)//2
            ty = size + (frame_h - th)//2 - 4
            # text color white or black based on brightness
            brightness = (fc[0]*299 + fc[1]*587 + fc[2]*114)/1000
            text_color = (0,0,0) if brightness>150 else (255,255,255)
            draw.text((tx,ty), text, fill=text_color, font=font)
            img = framed
        except Exception as e:
            print("frame error", e)

    return img

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
    # fallback to static
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
def register():
    data = request.get_json() or {}
    email = data.get("email","").strip().lower()
    password = data.get("password","")
    name = data.get("name","")
    if not email or not password:
        return jsonify({"error":"Email and password required"}), 400
    if len(password)<6:
        return jsonify({"error":"Password must be >=6 chars"}), 400
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
        # create default folder
        cur.execute("INSERT INTO folders (user_id,name,created_at) VALUES (?,?,?)", (uid,"My QR Codes",now))
        db.commit()
        token = jwt.encode({"user_id":uid,"email":email,"exp": datetime.datetime.utcnow()+datetime.timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALGO)
        db.close()
        return jsonify({"token":token,"user":{"id":uid,"email":email,"name":name}})
    except Exception as e:
        db.close()
        return jsonify({"error":str(e)}), 500

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email","").strip().lower()
    password = data.get("password","")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    db.close()
    if not row or not check_password_hash(row["password_hash"], password):
        return jsonify({"error":"Invalid credentials"}), 401
    token = jwt.encode({"user_id":row["id"],"email":email,"exp": datetime.datetime.utcnow()+datetime.timedelta(days=7)}, JWT_SECRET, algorithm=JWT_ALGO)
    return jsonify({"token":token,"user":{"id":row["id"],"email":email,"name":row["name"]}})

@app.route("/api/me", methods=["GET"])
@token_required
def me():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id,email,name,created_at,is_premium FROM users WHERE id=?", (g.user_id,))
    row = cur.fetchone()
    db.close()
    if not row:
        return jsonify({"error":"User not found"}), 404
    return jsonify(dict(row))

# --------------- API: Generate ---------------
@app.route("/api/generate", methods=["POST"])
def generate():
    """
    Expects JSON:
    {
      type: "url",
      data: { url: "..."},
      is_dynamic: bool,
      fg_color, bg_color, pattern, eye_style, frame_text, gradient,
      name
    }
    Or multipart with logo file
    """
    # handle both json and form
    if request.content_type and "multipart/form-data" in request.content_type:
        # form
        qr_type = request.form.get("type","url")
        data_json = request.form.get("data","{}")
        try:
            data = json.loads(data_json)
        except:
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
        # if data contains logo base64
        logo_b64 = body.get("logo_base64")
        if logo_b64:
            try:
                # save temp
                header, b64data = logo_b64.split(",",1) if "," in logo_b64 else ("", logo_b64)
                img_data = base64.b64decode(b64data)
                tmp_path = os.path.join(UPLOAD_DIR, f"tmp_{secrets.token_hex(4)}.png")
                with open(tmp_path,"wb") as f:
                    f.write(img_data)
                # we'll use this path
                logo_path_tmp = tmp_path
            except:
                logo_path_tmp = None
        else:
            logo_path_tmp = None

    # handle logo file save
    logo_path = None
    if 'logo_file' in locals() and logo_file:
        fname = secure_filename(logo_file.filename or "logo.png")
        tmp_name = f"{secrets.token_hex(6)}_{fname}"
        logo_path = os.path.join(UPLOAD_DIR, tmp_name)
        logo_file.save(logo_path)
    elif 'logo_path_tmp' in locals() and logo_path_tmp and os.path.exists(logo_path_tmp):
        logo_path = logo_path_tmp
    else:
        # also check if body has logo_path
        pass

    # Build content
    content = build_qr_content(qr_type, data)

    # For dynamic, create short code and store with redirect URL
    user_id = optional_auth()
    short_code = None
    final_content = content
    if is_dynamic:
        short_code = generate_short_code(8)
        # ensure unique
        db_tmp = get_db()
        for _ in range(5):
            cur = db_tmp.cursor()
            cur.execute("SELECT id FROM qrcodes WHERE short_code=?", (short_code,))
            if not cur.fetchone():
                break
            short_code = generate_short_code(8)
        db_tmp.close()
        # dynamic QR points to our redirect
        host = request.host_url.rstrip("/")
        final_content = f"{host}/r/{short_code}"

    # Security options
    password = None
    if request.is_json:
        body2 = request.get_json() or {}
        password = body2.get("password")
        scan_limit = body2.get("scan_limit")
        expiry_date = body2.get("expiry_date")
    else:
        password = request.form.get("password")
        scan_limit = request.form.get("scan_limit")
        expiry_date = request.form.get("expiry_date")

    pwd_hash = generate_password_hash(password) if password else None

    # Generate image
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
        # also svg? For now base64 png
        # Save to DB if user logged in
        qr_id = None
        if user_id:
            db = get_db()
            cur = db.cursor()
            now = datetime.datetime.utcnow().isoformat()
            cur.execute("""INSERT INTO qrcodes
            (user_id,folder_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,gradient,pattern,eye_style,frame_text,frame_color,logo_path,has_password,password_hash,expiry_date,scan_limit,scan_count,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, None, name, qr_type, content, json.dumps(data), 1 if is_dynamic else 0, short_code, fg_color, bg_color, gradient, pattern, eye_style, frame_text, frame_color, logo_path, 1 if pwd_hash else 0, pwd_hash, expiry_date, scan_limit, 0, now, now)
            )
            db.commit()
            qr_id = cur.lastrowid
            db.close()
        # cleanup tmp logo if not saved? keep if saved
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
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/api/preview", methods=["POST"])
def preview():
    """Quick preview without saving"""
    body = request.get_json() or {}
    content = body.get("content") or build_qr_content(body.get("type","url"), body.get("data",{}))
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
            tmp = os.path.join(UPLOAD_DIR, f"prev_{secrets.token_hex(4)}.png")
            with open(tmp,"wb") as f:
                f.write(img_data)
            logo_path = tmp
        except:
            pass
    img = create_qr_image(content, fg, bg, pat, eye, grad, logo_path, frame, fcol, size=800)
    b64 = image_to_base64(img)
    return jsonify({"image_base64": f"data:image/png;base64,{b64}"})

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
        # don't expose password hash
        d.pop("password_hash",None)
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
    # allowed fields
    fields=[]
    vals=[]
    for f in ["name","type","content","data_json","fg_color","bg_color","pattern","eye_style","frame_text","frame_color","folder_id"]:
        if f in body:
            fields.append(f"{f}=?")
            vals.append(body[f] if f!="data_json" or isinstance(body[f], str) else json.dumps(body[f]))
    if "password" in body:
        if body["password"]:
            fields.append("has_password=1")
            fields.append("password_hash=?")
            vals.append(generate_password_hash(body["password"]))
        else:
            fields.append("has_password=0")
            fields.append("password_hash=NULL")
    if "expiry_date" in body:
        fields.append("expiry_date=?"); vals.append(body["expiry_date"])
    if "scan_limit" in body:
        fields.append("scan_limit=?"); vals.append(body["scan_limit"])
    # Update content if data changed
    if "data" in body:
        new_content = build_qr_content(body.get("type", row["type"]), body["data"])
        fields.append("content=?"); vals.append(new_content)
        fields.append("data_json=?"); vals.append(json.dumps(body["data"]))
    # if is_dynamic content stays as short url, but update original content
    if fields:
        fields.append("updated_at=?"); vals.append(datetime.datetime.utcnow().isoformat())
        vals.append(qr_id); vals.append(g.user_id)
        sql = f"UPDATE qrcodes SET {', '.join(fields)} WHERE id=? AND user_id=?"
        cur.execute(sql, vals)
        db.commit()
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
    # Tiger rule: cannot delete if scans >=8? We keep but allow with warning - but enforce optional
    # For demo allow deletion anyway
    cur.execute("DELETE FROM qrcodes WHERE id=? AND user_id=?", (qr_id, g.user_id))
    cur.execute("DELETE FROM scans WHERE qr_id=?", (qr_id,))
    db.commit()
    db.close()
    return jsonify({"success":True})

@app.route("/api/qrcodes/bulk", methods=["POST"])
@token_required
def bulk_generate():
    # Expects CSV file with urls/names
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
            is_dyn=1
            short=generate_short_code(8)
            host=request.host_url.rstrip("/")
            final=f"{host}/r/{short}"
            # generate image not needed to store, but create DB entry
            now=datetime.datetime.utcnow().isoformat()
            cur.execute("INSERT INTO qrcodes (user_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,pattern,eye_style,scan_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (g.user_id,name,typ,content, json.dumps({"url":url}), is_dyn, short, fg,bg,"square","square",0,now,now))
            created.append({"name":name,"url":url,"short_code":short,"qr_url":final})
            if len(created)>=3000:
                break
        db.commit()
        db.close()
        return jsonify({"created":created, "count":len(created)})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/folders", methods=["GET","POST"])
@token_required
def folders():
    db=get_db()
    cur=db.cursor()
    if request.method=="POST":
        body=request.get_json() or {}
        name=body.get("name","New Folder")
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
    # scans over time last 7 days
    cur.execute("SELECT date(timestamp) as d, COUNT(*) as c FROM scans WHERE qr_id IN (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY date(timestamp) ORDER BY d DESC LIMIT 14", (g.user_id,))
    timeline=[dict(r) for r in cur.fetchall()]
    # device breakdown
    cur.execute("SELECT device, COUNT(*) as c FROM scans WHERE qr_id IN (SELECT id FROM qrcodes WHERE user_id=?) GROUP BY device", (g.user_id,))
    devices=[dict(r) for r in cur.fetchall()]
    # top QRs
    cur.execute("SELECT id,name,type,scan_count FROM qrcodes WHERE user_id=? ORDER BY scan_count DESC LIMIT 10", (g.user_id,))
    top=[dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify({"total_qrs":total,"total_scans":scans,"timeline":timeline,"devices":devices,"top":top})

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
    # aggregate by device/browser/os
    cur.execute("SELECT device, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY device", (qr_id,))
    devices=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT date(timestamp) as d, COUNT(*) as c FROM scans WHERE qr_id=? GROUP BY date(timestamp) ORDER BY d", (qr_id,))
    timeline=[dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify({"qr":dict(qr),"scans":scans,"devices":devices,"timeline":timeline})

@app.route("/r/<code>")
def redirect_dynamic(code):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE short_code=?", (code,))
    row=cur.fetchone()
    if not row:
        db.close()
        return "QR not found or expired",404
    # check expiry
    if row["expiry_date"]:
        try:
            exp=datetime.datetime.fromisoformat(row["expiry_date"])
            if datetime.datetime.utcnow()>exp:
                db.close()
                return "This QR has expired",410
        except:
            pass
    if row["scan_limit"] and row["scan_count"]>=row["scan_limit"]:
        db.close()
        return "Scan limit reached",410
    # password check
    if row["has_password"]:
        pwd = request.args.get("pwd") or request.args.get("password")
        if not pwd or not check_password_hash(row["password_hash"], pwd):
            # show password page
            db.close()
            return f"""
            <html style="font-family:Inter,sans-serif;background:#0A0A0A;color:white;display:flex;align-items:center;justify-content:center;min-height:100vh">
            <div style="background:#111;border:1px solid #222;padding:40px;border-radius:24px;max-width:400px;width:100%;text-align:center">
            <h2 style="color:#00FF88">🔒 Password Protected</h2>
            <p>This QR is protected by <b>NARE & CO.</b></p>
            <form>
              <input name="pwd" type="password" placeholder="Enter password" style="width:100%;padding:14px;border-radius:12px;border:1px solid #333;background:#000;color:white;margin:16px 0"/>
              <button style="width:100%;padding:14px;background:#00FF88;color:black;border:none;border-radius:12px;font-weight:800;cursor:pointer">Unlock</button>
            </form>
            <p style="font-size:12px;color:#888;margin-top:12px">Secured by NARE & CO. • Grid White / Black / Neon Green</p>
            </div></html>
            """,401
    # track scan
    ip=request.remote_addr or "127.0.0.1"
    ua=request.headers.get("User-Agent","")
    device,browser,os_name=detect_device(ua)
    now=datetime.datetime.utcnow().isoformat()
    # fake geo from ip? just use generic
    country="Unknown"
    city="Unknown"
    # rudimentary IP geo fake
    if ip.startswith("192") or ip=="127.0.0.1":
        country="Local"; city="Local"
    cur.execute("INSERT INTO scans (qr_id,timestamp,ip,user_agent,device,browser,os,country,city) VALUES (?,?,?,?,?,?,?,?,?)",
                (row["id"],now,ip,ua,device,browser,os_name,country,city))
    cur.execute("UPDATE qrcodes SET scan_count=scan_count+1, updated_at=? WHERE id=?", (now,row["id"]))
    db.commit()
    target=row["content"]
    db.close()
    # if content is JSON or vCard etc, show page not redirect
    if target.startswith("http"):
        return redirect(target, code=302)
    else:
        # For non-URL, show content page
        return f"""
        <html style="font-family:Inter,sans-serif;background:#F8F9FA;min-height:100vh"><body style="margin:0;padding:40px;background:
        radial-gradient(circle at 1px 1px, #e5e7eb 1px, transparent 0);background-size:22px 22px">
        <div style="max-width:640px;margin:0 auto;background:white;border:1px solid #0A0A0A;border-radius:20px;overflow:hidden;box-shadow:8px 8px 0 #0A0A0A">
        <div style="background:#0A0A0A;color:#00FF88;padding:16px 24px;display:flex;justify-content:space-between;align-items:center"><b>NARE & CO.</b><span style="font-size:12px;border:1px solid #00FF88;padding:4px 8px;border-radius:20px">SECURE QR</span></div>
        <div style="padding:32px"><h2>QR Content</h2><pre style="white-space:pre-wrap;background:#F8F9FA;padding:16px;border-radius:12px;border:1px solid #e5e7eb">{target[:2000]}</pre>
        <p style="color:#666;font-size:13px">Scanned via NARE & CO. dynamic QR • {device} • {browser}</p></div></div></body></html>
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
    # Re-generate image for download
    # Determine content (if dynamic, use short url)
    if row["is_dynamic"]:
        host=request.host_url.rstrip("/")
        content=f"{host}/r/{row['short_code']}"
    else:
        content=row["content"]
    img=create_qr_image(content, row["fg_color"], row["bg_color"], row["pattern"], row["eye_style"], row["gradient"], row["logo_path"], row["frame_text"], row["frame_color"], size=1200)
    buf=BytesIO()
    if fmt=="svg":
        # SVG fallback: save as PNG but rename
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png", as_attachment=True, download_name=f"nare-co-{qr_id}.png")
    elif fmt=="pdf":
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        pdf_buf=BytesIO()
        c=canvas.Canvas(pdf_buf, pagesize=A4)
        w,h=A4
        # draw title
        c.setFillColorRGB(0.04,0.04,0.04)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(40, h-60, "NARE & CO. — QR Code")
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.5,0.5,0.5)
        c.drawString(40, h-75, f"Type: {row['type']} • {row['name']} • Generated {row['created_at'][:10]}")
        # qr image
        img_buf=BytesIO()
        img.save(img_buf, format="PNG")
        img_buf.seek(0)
        ir=ImageReader(img_buf)
        c.drawImage(ir, 120, h-500, width=350, height=350, preserveAspectRatio=True, mask='auto')
        c.setFillColorRGB(0,1,0.53) # neon
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(w/2, h-520, row["frame_text"] or "Scan Me — NARE & CO.")
        c.showPage()
        c.save()
        pdf_buf.seek(0)
        return send_file(pdf_buf, mimetype="application/pdf", as_attachment=True, download_name=f"nare-co-{qr_id}.pdf")
    else:
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png", as_attachment=True, download_name=f"nare-co-{qr_id}.png")

@app.route("/api/qrcodes/<int:qr_id>/duplicate", methods=["POST"])
@token_required
def duplicate(qr_id):
    db=get_db()
    cur=db.cursor()
    cur.execute("SELECT * FROM qrcodes WHERE id=? AND user_id=?", (qr_id,g.user_id))
    row=cur.fetchone()
    if not row:
        db.close(); return jsonify({"error":"Not found"}),404
    new_code=generate_short_code(8) if row["is_dynamic"] else None
    now=datetime.datetime.utcnow().isoformat()
    cur.execute("""INSERT INTO qrcodes
    (user_id,folder_id,name,type,content,data_json,is_dynamic,short_code,fg_color,bg_color,gradient,pattern,eye_style,frame_text,frame_color,logo_path,has_password,password_hash,expiry_date,scan_limit,scan_count,created_at,updated_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (g.user_id, row["folder_id"], row["name"]+" (Copy)", row["type"], row["content"], row["data_json"], row["is_dynamic"], new_code, row["fg_color"], row["bg_color"], row["gradient"], row["pattern"], row["eye_style"], row["frame_text"], row["frame_color"], row["logo_path"], row["has_password"], row["password_hash"], row["expiry_date"], row["scan_limit"], 0, now, now))
    db.commit()
    nid=cur.lastrowid
    db.close()
    return jsonify({"id":nid})

# Health
@app.route("/api/health")
def health():
    return jsonify({"status":"ok","service":"NARE & CO.","version":"1.0.0","theme":"grid-white / black / neon-green"})

# Catch-all for frontend routes
@app.route("/<path:path>")
def catch_all(path):
    # try frontend file
    p=os.path.join(APP_DIR,"frontend",path)
    if os.path.isfile(p):
        return send_from_directory(os.path.join(APP_DIR,"frontend"), path)
    # fallback to index
    return send_from_directory(os.path.join(APP_DIR,"frontend"), "index.html") if os.path.exists(os.path.join(APP_DIR,"frontend","index.html")) else "Not found"

if __name__=="__main__":
    print("=== NARE & CO. ===")
    print("Grid White / Black / Neon Green")
    print("Server: http://localhost:5000")
    print("API docs: http://localhost:5000/api-docs")
    app.run(host="0.0.0.0", port=5000, debug=True)

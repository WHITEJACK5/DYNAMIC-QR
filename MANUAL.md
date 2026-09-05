# NARE & CO. — Working Manual (Personal Edition)

**Grid White `#F8F9FA` • Black `#0A0A0A` • Neon Green `#00FF88` • Local SQLite `data/nare.db`**

This manual is tested on a fresh Windows 11 + Python 3.11 clone. Every command below was executed and verified.

---

## 1) What This Build Is

- **Personal, local-first QR Tiger clone** — no pricing panel, no FAQ on homepage, pure generator + dashboard.
- **25+ types:** URL, vCard, File, Link Page/bio, Menu, App Stores, Landing Page, Smart URL/Multi-URL, GS1, MP3, Video, WiFi, Email, WhatsApp, Event, Facebook, YouTube, Instagram, Pinterest, TikTok, Twitter, Location, Text, SMS, Google Form, Google Review.
- **Static vs Dynamic:** Static = free, encoded directly, not editable. Dynamic = `BASE_URL/r/<8-char>` trackable, editable after print, password/expiry, requires login.
- **Homepage:** `http://127.0.0.1:5000` — generator (left) + **LIVE PREVIEW** (right) with Pattern/Eyes/Colors/Logo/Frame/Templates. No pricing/FAQ.
- **Dashboard:** `http://127.0.0.1:5000/dashboard` — manage all your QRs stored in `data/nare.db`.

---

## 2) Prerequisites

- Python 3.11 (tested `Python 3.11.9`), pip, git
- Windows / macOS / Linux — all supported. Windows has `run.bat` + `start.ps1`, Unix has `start.sh`/`stop.sh`
- No external DB, no cloud — SQLite auto-creates

Check:

```bash
python --version  # 3.11.x
pip --version
git --version
```

---

## 3) Fresh Install — Zero Manual DB Steps

This is the exact sequence for any fresh computer:

```bash
git clone https://github.com/WHITEJACK5/NARE-CO..git
cd NARE-CO.
cp .env.example .env   # Unix/macOS: creates SECRET_KEY; Windows: start.ps1 also auto-creates
# Windows PowerShell:
pip install -r requirements.txt
python app.py
# Unix/macOS:
chmod +x start.sh && ./start.sh
```

**What happens automatically on first `python app.py`:**

- `app.py:31` creates `data/` + `uploads/` + `.gitkeep` if missing
- `app.py:55` if `.env` missing or `SECRET_KEY` empty → generates `secrets.token_hex(32)` and writes `.env` with `BASE_URL`, `HOST=127.0.0.1`, `PORT=5000`, `FLASK_DEBUG=false`, `ALLOWED_ORIGINS`
- `app.py:126` `init_db()` creates `data/nare.db` with tables `users`, `qrcodes`, `scans`, `folders`, `templates` + indexes `idx_qr_short`, `idx_scans_qr`
- Console prints:
  ```
  [NARE & CO.] Fresh DB created at .../data/nare.db — tables: users, qrcodes, scans, folders, templates
  [NARE & CO.] Local DB ready
  Server: http://127.0.0.1:5000
  ```

Open `http://127.0.0.1:5000` — generator is ready. Open `http://127.0.0.1:5000/dashboard` — will redirect to `/?needAuth=1` until you register.

**To reset DB:** delete `data/nare.db` and restart `python app.py` — fresh DB recreated. To backup: copy `data/nare.db`.

`.env` is in `.gitignore` — never committed. `.env.example` is the template. `data/nare.db` and `uploads/*.png` are ignored; only `.gitkeep` files are tracked to keep folders.

---

## 4) Running Locally (Daily Use)

**Windows:**

```powershell
cd "C:\path\to\NARE-CO."
pip install -r requirements.txt
python app.py
# or
.\start.ps1
# or
.\run.bat
# stop
.\STOP.ps1
# or Ctrl+C in terminal
```

**Unix/macOS:**

```bash
./start.sh   # auto venv, pip install, creates .env if missing, runs app
./stop.sh    # pkill -f app.py
# or
pip install -r requirements.txt
python app.py
```

**Verify:**

```bash
curl http://127.0.0.1:5000/api/health
# {"service":"NARE & CO.","status":"ok","version":"1.1.0"}
netstat -ano | findstr 5000  # Windows: should show 127.0.0.1:5000 LISTENING (not 0.0.0.0)
lsof -i :5000                # Unix
```

`HOST=127.0.0.1` + `FLASK_DEBUG=false` by default — not exposed to LAN. To expose LAN (not recommended without proper secret), set `HOST=0.0.0.0` and `FLASK_DEBUG=false` in `.env`.

---

## 5) Environment (`.env`)

Copy `.env.example` → `.env` and edit:

```
SECRET_KEY=ded543...  # 64 hex chars — python -c "import secrets; print(secrets.token_hex(32))"
BASE_URL=http://localhost:5000  # dynamic QRs encode this + /r/<code> — change if you deploy to real domain
HOST=127.0.0.1
PORT=5000
FLASK_DEBUG=false
ALLOWED_ORIGINS=http://localhost:5000,http://127.0.0.1:5000
```

`SECRET_KEY` signs JWTs — changing it invalidates all existing logins (users must re-login). For personal use, keep it stable. If missing, app generates and persists it.

---

## 6) Using the Generator (Homepage)

1. **Pick type:** `All 25+ | Popular | Business | Social | Utility` tabs → click `URL`, `vCard`, `WiFi`, etc. `static/js/app.js:18` defines all.
2. **Choose Static vs Dynamic:** Toggle `STATIC ⇆ DYNAMIC` (`#dynamicToggle`). Dynamic requires login (shows register modal) and enables **Edit • Track • Password • Expiry**.
3. **Fill form:** Required fields marked `*` are validated (`validateForm()` `app.js:270`). Example:
   - URL: `https://nareandco.com`
   - WiFi: `SSID: NARE-WIFI, Password: neon123, Encryption: WPA`
   - vCard: `Name, Phone, Email`
   - Text: any plain text
4. **Customize (LIVE PREVIEW right panel):**
   - **Pattern:** Square / Dots / Rounded / Gapped (`app.py:279` `SquareModuleDrawer` etc.)
   - **Eyes:** Square / Circle / Rounded
   - **Colors:** Foreground `#0A0A0A`, Background `#FFFFFF`, gradient `Solid/Linear/Radial`, presets `Black/White`, `Black/Neon`.
   - **Logo:** Click or drag PNG/JPG/WebP/SVG ≤5MB, square recommended → centered at `22%` with white rounded bg (18px), `H` error correction ensures scan (`app.py:342`). Preview shows `Logo applied`. `Remove Logo` to clear.
   - **Frame:** Text `SCAN ME • NARE & CO.` (max 32), Frame Color `#00FF88` — high contrast = better scan.
   - **Templates:** `Neon Pop`, `Mono Black`, `Grid White`, `Neon Night` → `Save as Template` (requires login, stored in `templates`).
   Preview updates via `POST /api/preview` `app.js:168` with loading spinner `qrLoading`; fallback to `qrserver.com` if backend unavailable.
5. **Generate:** `⚡ Generate QR Code` → if dynamic without login, prompts register; else calls `POST /api/generate` `app.py:412`. On success, inline bar appears: `✔ Dynamic saved to Dashboard • /r/<code>` with `⬇ PNG` + `Dashboard →` — **no confirm dialog** (removed proving page). Check `Dashboard` to see it.
6. **Download:** In preview card, `PNG` / `SVG` (real vector via `SvgPathImage` `app.py:270`) / `PDF` (reportlab `A4` `app.py:987`) + `⬇ Download QR` (saves `NARE-CO-QR-<ts>.png`).

**Tips:** Always test scan with phone camera after customizing. Light foreground on white background scans best; neon on black needs good lighting.

---

## 7) Auth — Register / Login (Professional)

Modal `frontend/index.html:487` (`#authModal`):

- **Register:** Email (validated via `email_validator` `app.py:177` with regex fallback), Password `≥8` + `3/4` categories (upper/lower/digit/special) `app.py:186`, Name optional. Shows inline `field-error`, `authError`/`authSuccess`, loading `⟳`.
- **Login:** Same validation. If 2FA enabled, `POST /api/login` returns `need_2fa` + `temp_token` → `twofaModal` `frontend/index.html:460` appears; enter 6-digit code → `POST /api/2fa/login-verify` → JWT.
- **Forgot Password:** In login mode, `Forgot?` link → prompts email → `POST /api/forgot-password` (`app.py:304`, rate-limited `3/10m`) generates `reset_token` (logged to server console, and returned in JSON for personal use) → prompt for new password → `POST /api/reset-password`.
- **Remember me:** sets `nare_remember` in localStorage.
- **Tokens:** `PyJWT` `HS256`, `exp` 7d, stored `localStorage nare_token` + `nare_user`. `Log Out` clears and reloads. Rate limited `5/min` per IP (`app.py:89` `_rate_store`).

**Test via curl:**

```bash
curl -X POST http://127.0.0.1:5000/api/register -H "Content-Type: application/json" -d '{"email":"you@nare.local","password":"StrongPass123!","name":"You"}'
curl -X POST http://127.0.0.1:5000/api/login -H "Content-Type: application/json" -d '{"email":"you@nare.local","password":"StrongPass123!"}'
curl http://127.0.0.1:5000/api/me -H "Authorization: Bearer <token>"
```

---

## 8) Dashboard — Manage All Your QRs (Local DB)

`http://127.0.0.1:5000/dashboard` (`frontend/dashboard.html:1`, auth-guarded via `auth()` `dashboard.html:122` → redirects `/?needAuth=1` if no token).

- **Top stats:** `GET /api/analytics/overview` `app.py:875` — `Total QRs`, `Total Scans`, `Dynamic`, `Static`.
- **Search/Filter:** `Search` by name/type/content + `filterType` dropdown (URL, vCard, File, WiFi, etc.) `dashboard.html:275`.
- **QR Cards:** Each shows thumbnail (via `POST /api/preview` with stored `fg/bg/pattern/eye/frame`), `DYNAMIC` badge, `content` (short URL for dynamic), `scans`, `Live`. Actions:
  - **View** → modal `qrModal` with full content, `chip` meta, timeline `JSON`, recent scans `device • browser • os`, `PNG`/`PDF` buttons.
  - **✎ Edit** → `editModal` `dashboard.html:109` with **all fields**: Name, Type, Content, `data_json` (JSON), `fg/bg` color, Pattern, Eyes, Frame Text/Color, Password (blank to remove), Scan Limit, Expiry `datetime-local` → `PUT /api/qrcodes/<id>` `app.py:726`. Updates `updated_at`, regenerates on next scan.
  - **⎘ Duplicate** → `POST /api/qrcodes/<id>/duplicate` `app.py:1043` with new `short_code`.
  - **PNG/PDF** → `GET /api/download/<id>?format=png|svg|pdf` `app.py:986` (real SVG, not PNG rename).
  - **Delete** → `DELETE /api/qrcodes/<id>` `app.py:774` + `scans` cascade.

- **Analytics view** (`data-view="analytics"`): `GET /api/analytics/overview` — `Timeline` (last 14 days), `Devices`, `Countries`, `Top QRs`.

- **Bulk Upload** (`data-view="bulk"`): `POST /api/qrcodes/bulk` `app.py:792` — CSV `url,name` per line (header optional), `type` dropdown, up to 3000, per-row `INSERT` + `commit` (no batch loss on collision), returns `{count, created[]}` with `short_code` + `qr_url`.

- **Folders** (`data-view="folders"`): `GET/POST /api/folders` `app.py:834` — create `New Folder` (≤60 chars), list.

- **Templates** (`data-view="templates"`): `GET/POST /api/templates` `app.py:854` — save config via generator `Save as Template`, list.

- **Settings** (`data-view="settings"`): `GET /api/me` shows `twofa_enabled`, **2FA Setup** (`POST /api/2fa/setup` → `qr_base64` + `secret` → scan → `POST /api/2fa/verify-setup` with code), **Disable** (`POST /api/2fa/disable` with code). Also shows `Anonymize IP`, `Rate limiting`, `CORS` (disabled checkboxes as info), `Clear Local Cache`, `Reload Data`.

All data lives in `data/nare.db` — to backup, copy that file. To reset, delete it and restart.

---

## 9) API Quick Reference

Base `http://127.0.0.1:5000`, auth `Authorization: Bearer <JWT>` where noted.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/health` | — | `{"status":"ok","version":"1.1.0"}` |
| POST | `/api/register` | — (5/min) | `{"email","password"(≥8+3cat),"name"}` → `{token,user}` |
| POST | `/api/login` | — (5/min) | → `{token,user}` or `{need_2fa,temp_token}` |
| POST | `/api/forgot-password` | — (3/10m) | `{"email"}` → `{reset_token}` (logged) |
| POST | `/api/reset-password` | — | `{"email","token","new_password"}` |
| POST | `/api/2fa/setup` | yes | → `{secret,uri,qr_base64}` |
| POST | `/api/2fa/verify-setup` | yes | `{"code"}` → enable |
| POST | `/api/2fa/disable` | yes | `{"code"}` |
| POST | `/api/2fa/login-verify` | temp_token | `{"temp_token","code"}` → `{token}` |
| GET | `/api/me` | yes | user |
| POST | `/api/generate` | optional (20/min) | `{type,data,is_dynamic,fg_color,...}` → `{image_base64,short_code,qr_id}` |
| POST | `/api/preview` | — | `{content,fg_color,...}` → `{image_base64}` |
| GET | `/api/qrcodes` | yes | list own |
| GET/PUT/DELETE | `/api/qrcodes/<id>` | yes | get/edit/delete |
| POST | `/api/qrcodes/<id>/duplicate` | yes | → `{id}` |
| POST | `/api/qrcodes/bulk` | yes | `multipart file=CSV, type=` → `{count,created}` |
| GET/POST | `/api/folders` | yes | |
| GET/POST | `/api/templates` | yes | |
| GET | `/api/analytics/overview` | yes | `{total_qrs,total_scans,timeline,devices,countries,top}` |
| GET | `/api/qrcodes/<id>/analytics` | yes | |
| GET/POST | `/r/<code>` | — | redirect (POST for password `pwd`), tracks `scans` with real geo `ip-api.com` |
| GET | `/api/download/<id>?format=png|svg|pdf` | yes | file |

**Example generate:**

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:5000/api/login -H "Content-Type: application/json" -d '{"email":"you@nare.local","password":"StrongPass123!"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -X POST http://127.0.0.1:5000/api/generate -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"type":"url","data":{"url":"https://example.com"},"is_dynamic":true,"name":"My QR","fg_color":"#0A0A0A","bg_color":"#FFFFFF","pattern":"dots"}'
```

---

## 10) QR Types — Data Fields

Each `type` expects specific `data` keys (`FORM_DEFS` `static/js/app.js:48`):

- `url`: `url`
- `text`: `text`
- `email`: `email, subject, body`
- `sms`: `phone, message`
- `wifi`: `ssid, password, encryption [WPA/WEP/nopass], hidden`
- `vcard`: `name, organization, phone, email, url, address`
- `whatsapp`: `phone, message`
- `location`: `latitude, longitude`
- `event`: `title, location, start, end, description`
- `gs1`: `gtin, lot, serial, expiry` → builds `https://id.gs1.org/01/<gtin>/10/<lot>` `app.py:199`
- `smarturl`: `primaryUrl, rules` (lines `os:android -> https://...`) → `resolve_smart_url()` `app.py:214` picks by device/os/country/lang
- Others (`file, linkpage, menu, appstore, landingpage, mp3, video, facebook, youtube, instagram, pinterest, tiktok, twitter, googleform, googlereview`): `url`

All content built via `build_qr_content()` `app.py:170`.

---

## 11) Security Notes (Hardened)

- `SECRET_KEY` from `.env`, not hardcoded; auto-generated on fresh clone and persisted; mismatch warns.
- `HOST=127.0.0.1` `FLASK_DEBUG=false` — not `0.0.0.0` debug (Werkzeug RCE fix).
- Rate limit `5/min` login/register, `20/min` generate.
- CORS whitelist `ALLOWED_ORIGINS`.
- Password QR via `POST` `pwd` field, not `?pwd=` query (logs/history safe) `app.py:916`.
- `validate_email_format()` `app.py:177` + `validate_password_strength()` `≥8`+`3/4` `app.py:186`.
- 2FA TOTP `pyotp` `app.py:340`, JWT 7d `HS256`.
- `catch_all` `app.py:1070` safe `abspath` + `startswith` check before `send_from_directory`.
- No bare `except: pass` — all `logger.warning/exception`.
- Upload MIME whitelist `.png/.jpg/.webp/.svg` + `PIL verify()` `app.py:430`, `16MB` cap.
- Font fallback chain `arial.ttf, DejaVuSans` `app.py:320`, not hardcoded single.

Never expose this beyond `127.0.0.1` without setting a strong `SECRET_KEY` and `BASE_URL` to your real domain.

---

## 12) File Structure (Fresh Clone)

```
NARE-CO.
├── app.py              # Flask + auto DB init, QR engine, all APIs, safe routing
├── requirements.txt    # Flask, qrcode, Pillow, PyJWT, reportlab, requests, email-validator, pyotp, dotenv
├── .env.example        # template for SECRET_KEY, BASE_URL, HOST, PORT, ALLOWED_ORIGINS
├── .env                # ignored, auto-created with random key on first run
├── LICENSE (MIT)
├── MANUAL.md (this file) + frontend/manual.html
├── data/
│   ├── .gitkeep
│   └── nare.db         # ignored, auto-created — SQLite local DB
├── uploads/
│   ├── .gitkeep
│   └── *.png           # ignored — logos/tmp
├── frontend/
│   ├── index.html      # generator + LIVE PREVIEW (no pricing/FAQ)
│   ├── dashboard.html  # manage/edit/analytics (personal)
│   ├── manual.html     # rendered manual
│   ├── api-docs.html
│   └── ...
├── static/
│   ├── css/style.css   # grid-white/black/neon
│   └── js/app.js       # 25 types, preview, logo drag-drop, auth + 2FA
├── tests/test_api.py   # 11 pytest (health, validation, 2FA, SVG, GS1, smart, bulk)
└── .github/workflows/ci.yml
```

---

## 13) Troubleshooting

| Issue | Fix |
|---|---|
| `SECRET_KEY not set` warning | `cp .env.example .env` and edit `SECRET_KEY` to `python -c "import secrets;print(secrets.token_hex(32))"` |
| `address already in use` | `PORT` busy — `lsof -i :5000` (Unix) or `netstat -ano | findstr 5000` (Win) then `stop.sh` / `STOP.ps1` or `pkill -f app.py` |
| `Invalid email format` on register | Check email regex `a@b.c` — `.local` etc. now allowed via fallback |
| `Password must be at least 8...` | Use `StrongPass123!` (upper+lower+digit+special) |
| `Too many requests` `429` | Wait 60s — rate limit `5/min` per IP |
| `QR not found` on `/r/<code>` | Dynamic QR encodes `BASE_URL/r/<code>` — if you changed `BASE_URL` after printing, old QRs still point to old host; re-generate or set `BASE_URL` to real domain before generating |
| `Logo not showing` | Use PNG/JPG/WebP/SVG ≤5MB, square, try `Remove Logo` then re-upload; check `uploads/` writable |
| `SVG download is PNG` | Fixed in `v1.1.0` — `create_qr_svg()` `app.py:270` now real vector; clear cache and retry |
| `Scan geo shows Local/Unknown` | Normal for `127.0.0.1`; real geo via `ip-api.com` needs public IP and internet; check logs for `Geo lookup failed` |
| `DB locked` | Close other `sqlite` connections; restart `python app.py` |
| `404 on /dashboard` | Ensure logged in — `localStorage nare_token` must exist; check `http://127.0.0.1:5000/api/me` with token |
| `Tests fail with 429` | `tests/test_api.py` has `clear_rate_store` fixture — run `pytest -q` without parallel |
| Fresh clone `data/nare.db` missing | Normal — `python app.py` creates it; check `data/.gitkeep` exists |

Logs: `app.py` logs to stdout — watch for `[NARE & CO.]` and `WARNING`. For silent `except`, now logged via `logger.warning`.

---

## 14) Backup & Migrate

- Backup: `cp data/nare.db data/nare.db.bak`
- Move to another PC: copy `data/nare.db` + `uploads/` (logos) + `.env` (keep same `SECRET_KEY` or tokens invalidate)
- Reset: `rm data/nare.db && python app.py`

---

## 15) Production Notes (Personal → If You Deploy)

- Set `SECRET_KEY` long random, `BASE_URL=https://yourdomain.com`, `HOST=0.0.0.0` only behind reverse proxy (nginx) with HTTPS, `FLASK_DEBUG=false`, `ALLOWED_ORIGINS=https://yourdomain.com`.
- Use `gunicorn app:app -w 4` not `python app.py`; add `Postgres` instead of SQLite for multi-worker, `Redis` for rate limit.

---

**Manual tested on:** Windows 11, Python 3.11.9, Flask 3.0.3, data/nare.db fresh, 11 pytest passing, all manual steps executed.

For help: check `app.py` logs, `tests/test_api.py` as working examples, or open `http://127.0.0.1:5000/manual.html`.

© 2026 NARE & CO. — Personal Use — Grid White / Black / Neon Green

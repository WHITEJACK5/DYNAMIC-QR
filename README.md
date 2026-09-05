# NARE & CO. — QR Code Generator (Personal Use)

**Theme:** Grid White / Black / Neon Green  
**Location:** `C:\Users\BHARADWAJA REDDY\Downloads\ai_project\nare-and-co`  
**Personal build — Pricing & FAQ removed, local DB only**

Full QR Tiger clone for personal use — no pricing panel, no FAQ, pure generator + dashboard.

## Fresh Install — Zero Setup DB

When someone clones this repo on a **fresh computer**, everything auto-creates:

```powershell
git clone https://github.com/WHITEJACK5/NARE-CO..git
cd NARE-CO.
pip install -r requirements.txt
python app.py
# → [NARE & CO.] Fresh DB created at data/nare.db — tables: users, qrcodes, scans, folders, templates
# → [NARE & CO.] Local DB ready for personal use
# open http://localhost:5000
```

No manual DB steps. `app.py:31` creates `data/` + `uploads/` + `.gitkeep`, `app.py:51` `init_db()` creates SQLite `data/nare.db` with:

- `users` — email, password_hash (Werkzeug), name, created_at
- `qrcodes` — user_id, name, type, content, data_json, is_dynamic, short_code, fg/bg/gradient/pattern/eye/frame/logo, password, expiry, scan_count
- `scans` — qr_id, timestamp, ip, device/browser/os/country
- `folders`, `templates` + indexes on `short_code` and `qr_id`

If DB already exists, it loads: `DB loaded — users:X qrs:Y`. Deleting `data/nare.db` → next `python app.py` recreates fresh (tested).

## Features — Personal Edition

- **25+ QR Types:** URL, vCard, File, Link Page/bio, Menu, App Stores, Landing Page, Smart URL/Multi-URL, GS1, MP3, Video, WiFi, Email, WhatsApp, Event, Facebook, YouTube, Instagram, Pinterest, TikTok, Twitter, Location, Text, SMS, Google Form, Google Review
- **Static vs Dynamic:** Static free unlimited (no login), Dynamic (`/r/<short>` trackable, editable, password/expiry — requires login)
- **Logo Centre:** Drag & drop PNG/JPG/WebP/SVG (≤5MB, square recommended) → 22% centered, white rounded bg (18px), H-error correction — `app.py:342`, `static/js/app.js:392`
- **Customization:** Pattern (square/dots/rounded/gapped), Eyes, Colors + gradient, Frame CTA, Templates — live preview `POST /api/preview` with spinner, no overflow
- **Homepage:** Generator + Live Preview only — Pricing/FAQ removed, grid-white/black/neon, fully responsive, no breakouts
- **Auth — Professional:** `frontend/index.html:487` modal with email validation, password toggle, inline `field-error`, loading spinner, JWT 7-day (`localStorage nare_token`), error toasts for 409/401
- **Dashboard** `frontend/dashboard.html:1` — **Local DB managing:**
  - List/search/filter all your QRs, live thumbnails via `POST /api/preview`
  - **Full Edit** (`editModal`): name, type, content, data_json, fg/bg, pattern/eye, frame, password, scan_limit, expiry → `PUT /api/qrcodes/<id>` `app.py:726`
  - Duplicate `app.py:1043`, Delete, Download PNG/PDF `app.py:986`, Bulk CSV `app.py:792` (up to 3000), Folders `app.py:834`, Templates `app.py:854`
  - Analytics: `GET /api/qrcodes/<id>/analytics` + `GET /api/analytics/overview` `app.py:875` — scans, timeline, devices, top QRs
- **Security:** Werkzeug hash, JWT, password-protected `/r/<code>` (401 page), scan-limit/expiry (410), CORS, 16MB upload cap

## Quick Start (Personal)

```powershell
cd "C:\Users\BHARADWAJA REDDY\Downloads\ai_project\nare-and-co"
pip install -r requirements.txt
python app.py
# or .\start.ps1 / .\run.bat
```

**Test Health**
```powershell
curl http://localhost:5000/api/health
# {"service":"NARE & CO.","status":"ok"}
```

**Register + Generate Dynamic (saved to DB)**
```powershell
curl -X POST http://localhost:5000/api/register -H "Content-Type: application/json" -d '{"email":"you@nare.com","password":"123456","name":"You"}'
# → {token, user}
curl -X POST http://localhost:5000/api/generate -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"type":"url","data":{"url":"https://nareandco.com"},"is_dynamic":true,"fg_color":"#0A0A0A","bg_color":"#FFFFFF","pattern":"dots"}'
```

**List & Manage (DB)**
```powershell
curl -H "Authorization: Bearer <token>" http://localhost:5000/api/qrcodes
curl -X PUT -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"name":"New Name","fg_color":"#00FF88"}' http://localhost:5000/api/qrcodes/1
```

## Project Structure (Fresh Clone)

```
nare-and-co/
  app.py              # Flask + auto DB init (data/nare.db), QR engine, all APIs
  requirements.txt
  data/
    .gitkeep          # kept in git, DB auto-created on first run
    nare.db           # ignored by .gitignore — generated fresh per machine
  uploads/
    .gitkeep
  frontend/
    index.html        # Homepage — generator + live preview (no pricing/FAQ)
    dashboard.html    # Dashboard — full edit/manage/analytics (personal)
    api-docs.html
  static/
    css/style.css     # Grid white / black / neon green
    js/app.js         # 25 types, preview, logo, auth
```

## Design System

- Grid White: `#F8F9FA` + `#E9ECEF` 32px
- Black: `#0A0A0A` / `#111111`
- Neon: `#00FF88` / `#39FF14` / `#00E676` glow `0 0 20px rgba(0,255,136,0.5)`

## Notes for Other Computers

- No `.env` needed — SQLite file creates itself.
- To reset DB: delete `data/nare.db` → `python app.py` recreates.
- To backup: copy `data/nare.db`.
- Images/logos in `uploads/` are ignored by git (personal, local).

---
Built for **NARE & CO.** — Personal edition, local-first, single-command fresh install.

# NARE-CO.

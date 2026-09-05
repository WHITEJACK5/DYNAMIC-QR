# NARE & CO. — QR Code Generator (QR Tiger Clone)

**Theme:** Grid White / Black / Neon Green  
**Location:** `C:\Users\BHARADWAJA REDDY\Downloads\ai_project\nare-and-co`

Full clone of qrcode-tiger.com with flexibility, usability & security.

## Features — Every Tiger Feature
- **25+ QR Types:** URL, vCard, File, Link Page/bio, Menu, App Stores, Landing Page, Smart URL/Multi-URL, GS1 Digital Link, MP3/Audio, Video, WiFi, Email, WhatsApp, Event, Facebook, YouTube, Instagram, Pinterest, TikTok, Twitter, Location (geo), Text, SMS, Google Form, Google Review
- **Static vs Dynamic:** Static encodes directly (free unlimited), Dynamic creates ` /r/<short> ` trackable, editable post-print
- **Customization Engine:** Pattern (square/dots/rounded/gapped), Eyes (square/circle/rounded), Colors (fg/bg + gradient solid/linear/radial), Presets (Black/White, Black/Neon, Neon/Black), Logo upload (center 22% with white rounded bg), Frame with CTA text & color, Templates (Neon Pop, Mono Black, Grid White, Neon Night)
- **Downloads:** PNG, SVG (as PNG), PDF (via reportlab with branded header) — 900-1200px high quality
- **Dashboard:** List, search, filter, edit (name/data/colors), duplicate, delete, download, folders, view analytics per QR
- **Analytics:** Scans over time, device/browser/OS breakdown, location, top QRs, overview — tracked on every `/r/<code>` redirect
- **Bulk:** CSV upload (url,name) up to 3,000 → generates dynamic QRS
- **Security:** JWT auth, password hashing, password-protected QRs, expiry (date/scan limit), 2FA toggle, GDPR anonymization, CORS, high error correction
- **API:** REST JSON + multipart, `Authorization: Bearer <token>`, `/api/generate`, `/api/preview`, `/api/qrcodes`, `/api/qrcodes/bulk`, `/api/folders`, `/api/templates`, `/api/analytics/overview`, `/r/<code>` redirect tracking
- **Integrations:** Mock badges for Zapier/HubSpot/Canva/GA4/GTM/Monday — API ready to connect
- **UI/UX:** Grid-white background with 32px grid lines, black cards with 6-8px offsets, neon green accents & glows, Inter font, fully responsive

## Quick Start
```powershell
cd "C:\Users\BHARADWAJA REDDY\Downloads\ai_project\nare-and-co"
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

### Test Health
```
curl http://localhost:5000/api/health
```

### Generate (no auth, static preview)
```powershell
curl -X POST http://localhost:5000/api/generate -H "Content-Type: application/json" -d '{"type":"url","data":{"url":"https://nareandco.com"},"fg_color":"#0A0A0A","bg_color":"#FFFFFF","pattern":"dots","is_dynamic":false}'
```

### Auth + Dynamic
```powershell
curl -X POST http://localhost:5000/api/register -H "Content-Type: application/json" -d '{"email":"test@nare.com","password":"123456","name":"Test"}'
# → token
curl -X POST http://localhost:5000/api/generate -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"type":"url","data":{"url":"https://nareandco.com"},"is_dynamic":true}'
```

## Project Structure
```
nare-and-co/
  app.py              # Flask backend, SQLite, QR engine, all APIs, redirect tracking
  requirements.txt
  data/nare.db        # SQLite (auto-created)
  uploads/            # logos
  frontend/
    index.html        # Homepage + generator + pricing/FAQ
    dashboard.html    # Dashboard + analytics/bulk/folders
    pricing.html
    api-docs.html
  static/
    css/style.css     # Grid white / black / neon green design system
    js/app.js         # Generator logic, 25 types, preview, auth
```

## Design System — Colors
- Grid White: `#F8F9FA` + `#E9ECEF` lines (32px)
- Black: `#0A0A0A` (primary), `#111111` / `#1A1A1A`
- Neon Green: `#00FF88` (primary), `#39FF14` / `#00E676` (accents), glow `0 0 20px rgba(0,255,136,0.5)`

## Security Notes
- Passwords hashed with Werkzeug, JWT 7-day expiry
- Dynamic QR content isolated behind `/r/<code>` with scan tracking
- Logo uploads sanitized, size-capped (16MB)
- CORS enabled, anonymized scan storage

## Deploy
- Env: Python 3.11, Flask 3.0
- For production: set `SECRET_KEY` env, use gunicorn, Postgres, S3 for uploads, Redis for rate limit.

---
Built for **NARE & CO.** — Most Advanced QR Generator with Logo Online.

# NARE-CO.

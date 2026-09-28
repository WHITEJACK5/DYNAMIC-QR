# NARE & CO. — QR Code Generator (Personal Use)

**Theme:** Grid White / Black / Neon Green  
**Personal build — Pricing & FAQ removed, local DB only**

Full QR Tiger clone for personal use — no pricing panel, no FAQ, pure generator + dashboard.

## Fresh Install — Zero Setup DB

When someone clones this repo on a **fresh computer**, everything auto-creates:

```bash
git clone https://github.com/WHITEJACK5/NARE-CO..git
cd NARE-CO.
cp .env.example .env   # or use start.sh which auto-creates .env with random SECRET_KEY
pip install -r requirements.txt
python server.py
# → [NARE & CO.] Fresh DB created at data/nare.db — tables: users, qrcodes, scans, folders, templates
# → [NARE & CO.] Local DB ready for personal use
# open http://localhost:5000
```

No manual DB steps. `server.py` creates `data/` + `uploads/` + `.gitkeep`, `server.py` `init_db()` creates SQLite `data/nare.db` with:

- `users` — email, password_hash (Werkzeug), name, created_at
- `qrcodes` — user_id, name, type, content, data_json, is_dynamic, short_code, fg/bg/gradient/pattern/eye/frame/logo, password, expiry, scan_count
- `scans` — qr_id, timestamp, ip, device/browser/os/country
- `folders`, `templates` + indexes on `short_code` and `qr_id`

If DB already exists, it loads: `DB loaded — users:X qrs:Y`. Deleting `data/nare.db` → next `python server.py` recreates fresh (tested).

## Features — Personal Edition

- **25+ QR Types:** URL, vCard, File, Link Page/bio, Menu, App Stores, Landing Page, Smart URL/Multi-URL, GS1, MP3, Video, WiFi, Email, WhatsApp, Event, Facebook, YouTube, Instagram, Pinterest, TikTok, Twitter, Location, Text, SMS, Google Form, Google Review
- **Static vs Dynamic:** Static free unlimited (no login), Dynamic (`/r/<short>` trackable, editable, password/expiry — requires login)
- **Logo Centre:** Drag & drop PNG/JPG/WebP/SVG (≤5MB, square recommended) → 22% centered, white rounded bg (18px), H-error correction — `server.py`, `static/js/app.js:392`
- **Customization:** Pattern (square/dots/rounded/gapped), Eyes, Colors + gradient, Frame CTA, Templates — live preview `POST /api/preview` with spinner, no overflow
- **Homepage:** Generator + Live Preview only — Pricing/FAQ removed, grid-white/black/neon, fully responsive, no breakouts
- **Auth — Professional:** `frontend/index.html:487` modal with email validation, password toggle, inline `field-error`, loading spinner, JWT 7-day (`localStorage nare_token`), error toasts for 409/401
- **Dashboard** `frontend/dashboard.html:1` — **Local DB managing:**
  - List/search/filter all your QRs, live thumbnails via `POST /api/preview`
  - **Full Edit** (`editModal`): name, type, content, data_json, fg/bg, pattern/eye, frame, password, scan_limit, expiry → `PUT /api/qrcodes/<id>` `server.py`
  - Duplicate `server.py`, Delete, Download PNG/PDF `server.py`, Bulk CSV `server.py` (up to 3000), Folders `server.py`, Templates `server.py`
  - Analytics: `GET /api/qrcodes/<id>/analytics` + `GET /api/analytics/overview` `server.py` — scans, timeline, devices, top QRs
- **Security:** Werkzeug hash, JWT, password-protected `/r/<code>` (401 page), scan-limit/expiry (410), CORS, 16MB upload cap

## Quick Start (Personal)

```bash
# Unix/macOS
chmod +x start.sh && ./start.sh
# Windows PowerShell
pip install -r requirements.txt
python server.py
# or .\start.ps1 / .\run.bat / ./stop.sh
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
  server.py              # Flask app: thin HTTP handlers, versioned /api/v1 routes
  wsgi.py             # production entrypoint (gunicorn wsgi:application)
  alembic.ini         # migrations config (URL comes from the environment)
  core/               # everything except HTTP plumbing
    models.py         # SQLAlchemy models (the schema of record)
    db.py             # engine + session factory, dialect-specific pooling
    migrations.py     # programmatic upgrade/downgrade helpers
    qr_repo.py        # QR-code repository (all qrcodes-table access)
    users_repo.py     # users table
    scans_repo.py     # scans table
    folders_repo.py   # folders table
    templates_repo.py # templates table
    redirect_service.py  # pure redirect decisions (expiry/limit/password/smart URL)
    schemas.py        # Pydantic request schemas for every JSON route
    tokens.py         # JWT mint/verify
    storage.py        # logo storage (S3-compatible object storage)
    ratelimit.py      # rate limiting (Redis, in-memory fallback)
    jobs.py           # background jobs (RQ, thread fallback)
    cache.py          # read-through cache (Redis, in-memory fallback)
    pagination.py     # shared limit/offset parsing
    utils.py          # pure helpers (QR content builders, validation)
  migrations/
    versions/         # versioned, reversible schema migrations
  scripts/
    pgbackup.py       # pg_dump / pg_restore / verify
  data/
    .gitkeep          # kept in git, DB auto-created on first run
    nare.db           # ignored by .gitignore — SQLite path only
  uploads/
    .gitkeep          # used only when no S3 bucket is configured
  frontend/
    index.html        # Homepage — generator + live preview (no pricing/FAQ)
    dashboard.html    # Dashboard — full edit/manage/analytics (personal)
    api-docs.html
  static/
    css/style.css     # Grid white / black / neon green
    js/app.js         # 25 types, preview, logo, auth
  tests/              # 100 tests; PostgreSQL legs run when TEST_DATABASE_URL is set
```

## Database: SQLite (default) or PostgreSQL

The whole application runs on either database — the same repository code, no
SQLite-only paths. The dialect is chosen by one environment variable.

**SQLite (default, zero setup).** With `DATABASE_URL` unset the app creates and
migrates `data/nare.db` on first run. Copy the file to back it up.

**PostgreSQL.** Set `DATABASE_URL` and nothing else changes:

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/nare
python server.py          # runs `alembic upgrade head` on an empty database
```

```python
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/nare
DB_POOL_SIZE=5          # per worker process
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=1800
```

Each gunicorn worker and each RQ worker opens its own bounded pool
(`pool_pre_ping` on), so a recycled connection never surfaces as a request error.

### Schema changes are migrations, not inline DDL

There is no `CREATE TABLE` in application code. `migrations/versions/` holds
versioned, reversible migrations and the app upgrades on startup:

```bash
alembic upgrade head        # apply
alembic downgrade -1        # roll back one
alembic revision --autogenerate -m "add x"   # after editing core/models.py
```

A pre-Alembic `data/nare.db` is adopted by stamping it at head — your data is
never dropped.

### Backups

Managed PostgreSQL (RDS, Supabase, Railway) should use the provider's own
automated backups and PITR; enable them there. For self-hosted or containerised
databases, use the script in this repo:

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/nare
python -m scripts.pgbackup dump --out backups/nare-$(date +%F).dump
python -m scripts.pgbackup rotate --keep 14     # prune dumps older than 14 days
python -m scripts.pgbackup verify               # reachable + table count
```

Scheduling it is provided, not left to a comment. systemd:

```bash
echo 'DATABASE_URL=postgresql://user:password@localhost:5432/nare' \
  | sudo tee /etc/nare-backup.env && sudo chmod 600 /etc/nare-backup.env
sudo cp deploy/nare-backup.service deploy/nare-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nare-backup.timer
systemctl list-timers nare-backup.timer         # confirm next run
journalctl -u nare-backup.service              # read the log
```

Without systemd, use `deploy/crontab.example` (`crontab -l` plus that file).
Both run the same two commands above; `Persistent=true` / cron means a run
missed while the machine was off still happens.

Restore (drops and rebuilds the schema, then replays the dump):

```bash
python -m scripts.pgbackup restore --in backups/nare-2026-09-27.dump
```

Requires the PostgreSQL client tools (`pg_dump`, `pg_restore`, `psql`) on the
machine you run it from. **Copy dumps off the database host** — a dump next to
the database is not a backup.

## Logo storage

Uploaded logos go to S3-compatible object storage. This is required — there is no
silent local fallback, because a container's disk is ephemeral and a logo that
only exists on one box is data loss:

```bash
# .env — works with AWS S3, Cloudflare R2, Backblaze B2
S3_BUCKET=nare-logos
S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
AWS_REGION=auto
```

The database stores an `s3://bucket/key` reference. Behaviour when storage is not
usable is explicit:

| Situation | Result |
|---|---|
| No `S3_BUCKET`, no `ALLOW_LOCAL_STORAGE` | `503` on logo upload, naming the missing variable |
| S3 configured but the call fails | `503`, error logged; nothing written to local disk |
| `ALLOW_LOCAL_STORAGE=1` | Local `uploads/` used — dev/test only, logs a warning at startup |

`ALLOW_LOCAL_STORAGE` is opt-in and never inferred. Rows written while it was
enabled keep rendering while it stays enabled. Preview logos are never persisted.

## Design System

- Grid White: `#F8F9FA` + `#E9ECEF` 32px
- Black: `#0A0A0A` / `#111111`
- Neon: `#00FF88` / `#39FF14` / `#00E676` glow `0 0 20px rgba(0,255,136,0.5)`

## Notes for Other Computers

- No `.env` needed for the SQLite path — the file creates itself and is migrated
  on first run.
- To reset the SQLite DB: delete `data/nare.db` → `python server.py` recreates it.
- To back up SQLite: copy `data/nare.db`. To back up PostgreSQL: see Backups above.
- Images/logos in `uploads/` are ignored by git (used only when no S3 bucket is configured).

---

Built for **NARE & CO.** — Personal edition, local-first, single-command fresh install.

# NARE-CO.

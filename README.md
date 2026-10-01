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
  server.py              # composition root + dev entrypoint (app.run, dev only)
  wsgi.py                # production entrypoint (gunicorn wsgi:application)
  alembic.ini            # migrations config (URL comes from the environment)
  app/
    routes/              # HTTP layer: thin handlers on Blueprints
      auth.py            #   register / login / 2FA
      qr.py              #   generate / CRUD / download / preview
      analytics.py       #   scan and aggregate analytics
      redirect.py        #   /r/<code> — the public redirect path
      meta.py            #   health, version, pagination meta
      pages.py           #   frontend page serving
    services/            # business logic
      render.py          #   QR rendering (patterns, frames, gradients, logos)
      redirect_service.py#   redirect decisions (expiry/limit/password/smart URL)
      geo.py             #   IP geolocation (off the redirect path)
      tokens.py          #   JWT mint/verify
      storage.py         #   logo storage (S3-compatible object storage)
    repositories/        # all SQL, session-based
      users_repo.py      #   users table
      qr_repo.py         #   qrcodes table
      scans_repo.py      #   scans table
      folders_repo.py    #   folders table
      templates_repo.py  #   templates table
    models/              # data models (the schema of record)
      entities.py        #   SQLAlchemy ORM declarations
    utils/               # pure helpers, no Flask/DB/network
      qr_content.py      #   QR payload construction per type
      validation.py      #   colour parsing, short codes, password checks
      device.py          #   user-agent parsing
    schemas.py           # Pydantic request schemas for every JSON route
    db.py                # engine + session factory, dialect-specific pooling
    config.py            # environment + secret bootstrap
    extensions.py        # app object, CORS, auth decorators, limiter
    jobs.py              # background jobs (RQ, thread fallback)
    cache.py             # read-through cache (Redis, in-memory fallback)
    ratelimit.py         # rate limiting (Redis, in-memory fallback)
    pagination.py        # shared limit/offset parsing
    migrations.py        # programmatic upgrade/downgrade helpers
  migrations/            # Alembic: env.py + versions/
  scripts/pgbackup.py    # pg_dump / pg_restore / verify / rotate
  deploy/                # nginx, systemd backup unit + timer, crontab example
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
  tests/              # unit + integration; PostgreSQL legs run when TEST_DATABASE_URL is set
```

## Security headers

Every response carries `Content-Security-Policy`, `X-Content-Type-Options:
nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`X-DNS-Prefetch-Control: off` and `Cross-Origin-Opener-Policy: same-origin`.
`Strict-Transport-Security` is added only on HTTPS requests (nginx sets
`X-Forwarded-Proto`), so plain-HTTP development is not pinned to TLS.

The policy is in `app/security.py` and is written for what this app actually
serves:

| Directive | Why |
|---|---|
| `script-src 'self' 'unsafe-inline'` | no CDN is used, but the raw-HTML frontend still has inline handlers |
| `style-src` + `font-src` allow Google Fonts | every page loads Inter/JetBrains Mono from there |
| `img-src 'self' data:` | QR previews are base64 data URIs |
| `object-src 'none'`, `frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'` | plugins, framing and base-tag injection are all unnecessary here |

**`unsafe-inline` for scripts is the weakest part of this policy** and is
recorded as such: the current frontend has 33 inline `onclick` handlers and an
inline `<script>`. Phase 8's React + TypeScript build with a hashed bundle
removes the need for it. `tests/test_security_headers.py` fails if the inline
handlers disappear without the policy being tightened to match.

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
alembic revision --autogenerate -m "add x"   # after editing app/models/entities.py
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

## Secrets

`.env` is for **local development only**. It is git-ignored, and CI fails if it
is ever committed.

In staging and production the secret comes from the host's secret store, which
injects it as an environment variable:

| Host | Where the secret goes |
|---|---|
| Render | Dashboard → your service → Environment → Add secret |
| Railway | project → Variables → add `SECRET_KEY` |
| Fly.io | `fly secrets set SECRET_KEY=...` |
| AWS | Secrets Manager / SSM, exported by the task definition |

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Two behaviours make a misconfigured deploy fail loudly instead of quietly:

- **Production refuses to start without `SECRET_KEY`.** Previously the app
  generated one and wrote it into the container filesystem — a key that dies
  with the container, invalidating every session on the next restart, while
  the deploy still looked healthy. The error names each provider above.
- **Production does not read `.env` at all.** A file baked into the image, or
  left over from an earlier build, would otherwise silently shadow the
  injected secret. If one is present the app logs a warning naming the path.

Production is detected from the variables those platforms set (`RENDER`,
`RAILWAY_ENVIRONMENT`, `FLY_APP_NAME`, `DYNO`, `KUBERNETES_SERVICE_HOST`), or
by setting `APP_ENV=production` explicitly. A container on an unrecognised host
is treated as development, so a fresh clone still works with zero setup.

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

## Pagination

List endpoints use **`limit` / `offset`** (offset pagination):

```bash
GET /api/v1/qrcodes?limit=50&offset=0
GET /api/v1/folders?limit=20&offset=40
GET /api/v1/templates?limit=20&offset=0
GET /api/v1/qrcodes/<id>/analytics?limit=100&offset=0   # the scan list
```

Paginated responses are an envelope:

```json
{ "items": [ ... ], "total": 128, "limit": 50, "offset": 0 }
```

Two behaviours worth knowing:

- **Defaults are backwards compatible.** With no `limit`/`offset`, the
  collection endpoints return a bare array (the legacy shape older clients
  depend on). Supply either parameter and you get the envelope. This is a
  real inconsistency in the API rather than something to hide — it is
  recorded in `app/api_contract.py` under `LEGACY_BARE_LIST`.
- **Bad input is a 400**, not a silently clamped page: a non-numeric or
  out-of-range `limit` is rejected.

## Known limitations

- **Token revocation depends on Redis not being flushed.** Outstanding
  revocations live in Redis; a flush un-revokes them. That keyspace needs a
  persistent Redis with an eviction policy that does not target it.
- **The CSP needs `script-src 'unsafe-inline'`** until Phase 8 replaces the
  raw-HTML frontend.
- **A malformed `scan_limit` is rejected, not coerced** (400). This is a
  deliberate behaviour change: it used to become "no limit", so a merchant
  whose value arrived mangled silently got an unlimited QR. Both the JSON and
  multipart paths share the rule, so neither is looser than the other.
- **Load-test figures come from one machine**, not a production host. CI runs
  on Linux with gunicorn; local runs on Windows fall back to waitress.

## Tests and coverage

```bash
pytest -q                                    # SQLite
TEST_DATABASE_URL=postgresql://… pytest -q   # + PostgreSQL legs
pytest -q --cov                              # + coverage, enforced threshold
```

**Coverage: 74.40%** (branch coverage over `app/`, `server.py`, `wsgi.py`)
against a **70% floor** that fails the build. Reproduce the number with the
command above; CI runs the same command and uploads `coverage.xml`.

The floor is deliberately below the measured value. Pinning it to the current
number would fail the build the first time a line was legitimately added,
which teaches a team to lower the floor rather than write tests. It is a
ratchet, not a target — raise it as coverage genuinely improves.

There is **no coverage badge**. A shields.io badge needs a coverage service
(coveralls/Codecov) or a scheduled job publishing the figure, and neither is
set up, so a badge would display a number nothing keeps current. The number
above is measured, not decorated.

Heavy suites, each with extra tooling and each run by its own CI step:

| Suite | Needs | What it covers |
|---|---|---|
| `tests/test_e2e_playwright.py` | `pip install playwright && playwright install chromium` | Real browser: register → verify from a real email → login → dynamic QR → scan → analytics |
| `tests/test_load_redirect.py` | k6 on PATH | The `/r/<code>` redirect under sustained load, against the thresholds in `loadtests/redirect.js` |

Run the load profile directly:

```bash
BASE_URL=http://127.0.0.1:8000 CODE=abc12345 k6 run loadtests/redirect.js
QUICK=1 … k6 run loadtests/redirect.js   # light profile for CI
```

## Deployment architecture

```mermaid
%% Rendered by GitHub from docs/architecture.mmd. The diagram is the text,
%% so it cannot drift from what the code actually does.
flowchart LR
    subgraph client["Client"]
        B["Browser / phone camera"]
    end
    subgraph edge["Edge"]
        CDN["CDN<br/>static assets + TLS termination"]
        LB["Reverse proxy<br/>nginx"]
    end
    subgraph app["App tier — containerised, horizontally scalable"]
        W1["gunicorn worker<br/>wsgi:application"]
        W2["gunicorn worker<br/>wsgi:application"]
        J["RQ worker<br/>geo enrichment, bulk CSV"]
    end
    subgraph data["Data tier"]
        PG[("PostgreSQL 16<br/>users · qrcodes · scans<br/>folders · templates")]
        RD[("Redis 7<br/>rate limits · revocation<br/>job queue · cache")]
        S3[("S3-compatible object storage<br/>logos")]
    end
    B -->|"HTTPS"| CDN
    CDN -->|"proxy_pass"| LB
    LB -->|"gunicorn"| W1
    LB -->|"gunicorn"| W2
    W1 -->|"SQLAlchemy"| PG
    W2 -->|"SQLAlchemy"| PG
    W1 -->|"cache / rate limit"| RD
    W2 -->|"cache / rate limit"| RD
    W1 -->|"put_object"| S3
    J -->|"SQLAlchemy"| PG
    J -->|"enqueue / dequeue"| RD
    classDef client fill:#0A0A0A,stroke:#00FF88,color:#fff
    classDef edge fill:#111,stroke:#555,color:#eee
    classDef app fill:#1a1a2e,stroke:#00FF88,color:#eee
    classDef data fill:#0d1b2a,stroke:#4a9eff,color:#eee
    class B client
    class CDN,LB edge
    class W1,W2,J app
    class PG,RD,S3 data
```

The source of truth is [`docs/architecture.mmd`](docs/architecture.mmd) —
GitHub renders it from there, so the diagram is reviewable text and cannot
silently drift from the code.

**What each hop is for, and what it is not:**

| Hop | Why it exists |
|---|---|
| Client → CDN | TLS termination and static asset caching at the edge, so the app tier never serves a static file or negotiates TLS |
| CDN → nginx | `deploy/nginx.conf` is the only thing that talks to gunicorn. It sets `X-Forwarded-Proto`, which `app/security.py` reads to decide whether to send HSTS |
| nginx → gunicorn | `wsgi:application` is the production entrypoint. `app.run()` is dev-only and is never the container CMD |
| app → PostgreSQL | SQLAlchemy with a bounded pool (`pool_pre_ping`, dialect-specific sizing) |
| app → Redis | Rate limiting, token revocation, the job queue and the read-through cache — one store, shared across workers |
| app → S3 | Logos only. Local disk is not the system of record (Phase 3d) |
| RQ worker → Postgres/Redis | Background jobs (geo-IP enrichment, bulk CSV) run outside the request path so they cannot delay a redirect |

**Secrets are deliberately absent from this diagram.** They are not in the
repository, not in the image, and not in compose — they arrive from the
host's secret store as environment variables. See [Secrets](#secrets).

**Local development** uses the same topology with one command:

```bash
cp .env.example .env
docker compose up --build
```

which brings up app + PostgreSQL + Redis + the RQ worker. See
[Tests and coverage](#tests-and-coverage) for the suite that drives the
running stack end to end.

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

# Engineering Directive — DYNAMIC-QR Production Readiness

> Authoritative spec for this repository. Saved here so every later session works
> from the document, not from recollection. If this file and a chat message ever
> disagree, this file wins.

**Role:** Senior Software Development Engineer (8+ years), acting as tech lead, with full
authority to refactor, restructure, and re-architect. Take this repository from
"hackathon prototype" to "production-grade, resume-defensible, interview-defensible
service." No corners cut, no impressive-sounding features that aren't real, and nothing
is touched without leaving it more correct, more tested, and more explainable.

**Repository:** `WHITEJACK5/DYNAMIC-QR` (Flask + SQLite QR-code generation/analytics
service, "DRQR")

**Mandate:** Work through every item below, in order, as its own atomic, reviewable unit
of work. Do not batch unrelated fixes into one commit. Do not mark anything done until
it has a test proving it, or a manual verification step documented in the PR
description.

---

## Ground rules for every change

1. One concern per branch, one branch per PR. Branch names: `fix/<short-slug>`,
   `feat/<short-slug>`, `chore/<short-slug>`.
2. Every PR must pass CI before merge. CI must run: lint, type-check (where applicable),
   unit tests, and a build/Docker build step.
3. Every PR description states: what changed, why, how it was verified, and what (if
   anything) it breaks or requires a migration for.
4. No PR should ever again touch more than ~300 lines across more than ~5 files. If it
   does, it is not one concern — split it.
5. No claim goes on a public page (README, pricing page, landing page) that is not
   literally true of the current running system.
6. Never invent metrics, uptime numbers, or compliance badges. If a claim can't be
   substantiated with a link to actual config/infra, delete it.

---

## Phase 1 — Stop the bleeding (credibility & correctness, do first)

- [ ] **Remove all fabricated claims** from `frontend/pricing.html` and anywhere else in
  the frontend: "60B+ clicks/yr", "99.9% uptime", "GDPR • CCPA" badges. Replace with
  nothing, or with an honest "in development" note if a pricing page is kept at all.
- [ ] **Fix the dead/stub page**: `frontend/analytics.html` is a redirect stub with no
  content. Either build it out as a real page or remove the route/link entirely — do not
  ship dead pages.
- [ ] **Fix the pre-`logger` reference bug** in the `SECRET_KEY` bootstrap block (`app.py`,
  the `.env` auto-write path) — `logger.warning(...)` is called before
  `logger = logging.getLogger("DR")` is defined. Reorder initialization so logging is
  configured before first use, and add a test that exercises the "no SECRET_KEY set"
  cold-start path.
- [ ] **Remove the third-party data leak** in `static/js/app.js` (`api.qrserver.com`
  fallback in the preview function). Either make the internal `/api/preview` endpoint
  reliable enough not to need a fallback (with proper error handling and a retry), or
  explicitly disclose to the user that failed previews fall back to an external service —
  but the default should be "fail with a clear error," not "silently exfiltrate user input
  to an undisclosed third party."
- [ ] **Stop external geo-IP calls from blocking the redirect path.** `get_geo_from_ip()`
  is called synchronously inside `/r/<code>` with two chained external HTTP calls (2s
  timeout each). Either: (a) move this to an async background task fired after the
  redirect response is already sent, (b) queue it (see Phase 5, job queue), or (c) remove
  third-party geo-IP entirely and rely only on data you already have (e.g.,
  `Accept-Language`, or defer to a CDN's geo headers post-deployment). The redirect
  response must return before any analytics/geo work happens.

## Phase 2 — Backend architecture (the 1,800-line monolith)

- [ ] **Split `app.py` into layers.** Minimum structure:
  - `app/routes/` — thin HTTP handlers only (parse request, call service, return response)
  - `app/services/` — business logic (QR generation, analytics, auth logic)
  - `app/repositories/` — all DB access, isolated behind an interface
  - `app/models/` — data models/schemas
  - `app/utils/` — pure helper functions (color parsing, short-code generation, etc.)
- [ ] **Introduce request/response validation schemas** (Pydantic or Marshmallow) for
  every route currently doing manual `if key in body` checks. Every endpoint gets an
  explicit input schema and a documented output schema.
- [ ] **Add API versioning**: all routes move under `/api/v1/...`. Old unversioned routes
  either 410 or proxy to v1 during a deprecation window.
- [ ] **Add pagination** to `GET /api/qrcodes` and any other list endpoint (`limit`/`offset`
  or cursor-based — pick one and document it).
- [ ] **Replace the in-memory rate limiter** (`_rate_store = {}`) with Redis-backed rate
  limiting (`Flask-Limiter` + Redis backend). Must survive process restarts and work
  correctly across multiple worker processes.
- [ ] **Introduce a background job queue** (Celery, RQ, or Dramatiq — pick one) for:
  geo-IP enrichment, bulk CSV QR generation, any future email sending. Nothing that isn't
  strictly required for the HTTP response should run inline in the request thread.
- [ ] **Add a caching layer** (Redis) for read-heavy endpoints — QR preview results for
  identical inputs, analytics overview queries.
- [ ] **Serve via a real WSGI server.** Replace `app.run(...)` with gunicorn (or uWSGI)
  behind nginx (or equivalent reverse proxy) in the deployment config. `app.run()` is
  dev-only — this must never be the production entrypoint again.

## Phase 3 — Data layer

- [ ] **Migrate SQLite → PostgreSQL.** Introduce SQLAlchemy as the ORM layer (this also
  gives you the repository pattern for free).
- [ ] **Add a migrations framework** (Alembic). No more hand-written
  `CREATE TABLE IF NOT EXISTS` inline in Python — every schema change is a versioned,
  reversible migration file.
- [ ] **Move uploaded logos to object storage** (S3-compatible — AWS S3, Cloudflare R2, or
  Backblaze B2). Local disk storage must not survive this refactor.
- [ ] **Set up automated backups** for the Postgres instance (most managed Postgres
  providers — RDS, Supabase, Railway — offer this natively; enable it, document the
  restore procedure).
- [ ] **Add connection pooling** configuration for the Postgres connection.

## Phase 4 — Security hardening

- [ ] **Remove JWT-via-query-param support entirely.** Token must come from the
  `Authorization: Bearer` header only (or a proper `HttpOnly`, `Secure`, `SameSite` cookie
  with CSRF protection if you keep cookie-based auth).
- [ ] **Add refresh tokens** with short-lived (15 min) access tokens, and a token
  revocation list (Redis-backed) so compromised tokens can actually be invalidated before
  natural expiry.
- [ ] **Add email verification** on registration before an account can create dynamic QR
  codes.
- [ ] **Add security headers**: `Content-Security-Policy`, `X-Content-Type-Options`,
  `X-Frame-Options`, `Strict-Transport-Security` (via `flask-talisman` or equivalent).
- [ ] **Add CSRF protection** for any cookie-authenticated state-changing route.
- [ ] **Add dependency + secret scanning to CI**: Dependabot (or Renovate) for dependency
  updates, `gitleaks` or `truffleHog` for secret scanning, and a basic SAST pass (`bandit`
  for Python).
- [ ] **Move secrets out of `.env` files** for any real deployment — use the hosting
  provider's secrets manager (Render/Railway secrets, AWS Secrets Manager, etc.) in
  staging/production; `.env` remains local-dev-only.

## Phase 5 — Testing & QA

- [ ] **Add authorization boundary tests**: verify user A cannot read/update/delete user
  B's QR codes by guessing/incrementing IDs. This is currently untested and is a real
  vulnerability class if it's broken.
- [ ] **Add concurrency tests** around scan-count increments and short-code generation
  collisions.
- [ ] **Add end-to-end tests** (Playwright) covering: register → login → generate dynamic
  QR → scan it → see it in analytics.
- [ ] **Add load testing** (k6 or Locust) for the `/r/<code>` redirect path specifically —
  this is the path real users hit and it must be proven fast under load.
- [ ] **Add coverage reporting** to CI (e.g., `pytest-cov` + a coverage badge in the
  README) with a minimum threshold that fails the build if not met.

## Phase 6 — DevOps / Infrastructure

- [ ] **Write a Dockerfile** for the app and a `docker-compose.yml` that brings up app +
  Postgres + Redis together with one command.
- [ ] **Set up a staging environment** distinct from production, deployed automatically
  from a `staging` branch.
- [ ] **Add a CD pipeline**: on merge to `main`, run full CI, then deploy to production
  automatically (or with a manual approval gate) — actually wire this up, don't just have
  a CI file that runs tests and stops.
- [ ] **Document the deployment architecture** in the README with an actual diagram (even a
  simple draw.io/Excalidraw export): client → CDN/reverse proxy → app servers →
  Postgres/Redis.

## Phase 7 — Observability

- [ ] **Add error tracking** (Sentry free tier) wired into both backend and frontend.
- [ ] **Add structured logging** (JSON logs) instead of ad-hoc
  `print()`/`logger.info(f"...")` string interpolation.
- [ ] **Add basic uptime monitoring** (UptimeRobot, BetterStack, or similar free tier)
  pointed at the deployed health endpoint.
- [ ] **Add basic metrics** (request count, latency, error rate per route) — even a simple
  Prometheus + Grafana setup, or a hosted equivalent, is enough to credibly claim
  "observability" in an interview.

## Phase 8 — Frontend

- [ ] **Rebuild the frontend in React + TypeScript** (or Next.js if you want SSR/SEO
  benefits for the marketing pages), replacing the current multi-page raw HTML/JS setup.
  Component-ize the shared header/nav/footer that is currently copy-pasted across every
  page.
- [ ] **Add accessibility basics**: semantic HTML, ARIA labels on interactive elements,
  keyboard navigation support, color-contrast check against WCAG AA.
- [ ] **Add a build pipeline** (Vite) with linting (ESLint) and formatting (Prettier)
  enforced in CI.
- [ ] **Add basic performance budgeting** — Lighthouse CI in the pipeline with a score
  threshold that fails the build if regressed.

## Phase 9 — API documentation & contracts

- [ ] **Generate a real OpenAPI/Swagger spec** from the validation schemas introduced in
  Phase 2, and serve it at `/api/v1/docs` (e.g., via `flask-smorest` or `apiflask`).
  Replace the current static `api-docs.html` with this generated, always-accurate spec.

## Phase 10 — The actual product gap (do this after Phases 1–9 land)

- [ ] **Add a review-capture flow**: scanning a dynamic QR of type `review` should route
  the customer to a lightweight review form (rating + free text), not just redirect to a
  static link.
- [ ] **Add an LLM-based sentiment/summarization feature** on top of captured reviews:
  sentiment classification per review, and a short auto-generated "what customers are
  saying" summary on the vendor dashboard. Use a hosted LLM API
  (Anthropic/OpenAI/Gemini) behind the background job queue from Phase 2 — do not call it
  synchronously from a request handler.
- [ ] **Add a vendor-facing dashboard view** distinct from the current QR-management
  dashboard: aggregate rating trend over time, flagged negative reviews needing response,
  exportable report.

---

## Definition of done for this entire directive

- Every checkbox above has a merged PR, linked from a tracking issue, with a passing CI
  run and a test or documented manual verification.
- The README accurately describes the current architecture, with no forward-looking or
  aspirational claims stated as fact.
- The app is deployed and reachable at a public URL, running Postgres + Redis + the
  containerized app behind gunicorn/nginx.
- A fresh clone of the repo can be brought up locally with `docker-compose up` and no
  manual steps beyond copying an `.env.example`.

Work top to bottom. Do not skip ahead to Phase 10 to make the project "sound" more
impressive before Phases 1–7 are real — an interviewer will find the gap in thirty seconds
of follow-up questions.

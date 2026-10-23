# DRQR — Frontend Architecture

Status: current as of branch `chore/amber-palette`.
Derived from the source, not from design intent.

---

## 1. Scope

This document describes the browser-facing half of DRQR: how pages are served,
how the two frontend shells are built and loaded, how state and data flow
through them, what each screen is composed of, and what every interactive
control does.

Backend internals (models, workers, storage) are described only where the
frontend depends on them.

---

## 2. System context

DRQR is a self-hosted QR code generator. A Flask application serves both the
pages and a JSON API from the same origin, so the frontend never needs CORS or
a configurable API host.

```
                    ┌─────────────────────────────┐
   browser  ──────► │  Flask (server.py / wsgi)   │
                    ├─────────────────────────────┤
                    │  pages.py    HTML + assets  │
                    │  auth.py     sessions, 2FA  │
                    │  qr.py       generate, CRUD │
                    │  analytics   scan counts    │
                    │  meta.py     folders, tpl   │
                    │  redirect.py /r/<code>      │
                    └──────────┬──────────────────┘
                               │
                     SQLite / PostgreSQL
```

Two consequences shape the whole frontend:

1. **Same origin.** `const API = location.origin` in both scripts. There is no
   client-side environment switch; development relies on the Vite proxy.
2. **Server-rendered shell, client-rendered body.** Flask returns complete HTML
   documents. Everything after first paint is DOM mutation from plain scripts.

---

## 3. Technology stack

| Layer | Choice |
|---|---|
| Page server | Flask, Jinja-free static file serving |
| Legacy UI | Hand-written HTML + CSS + vanilla ES2017 |
| React UI | React 18 + TypeScript 5.6 |
| Bundler | Vite 6 (`tsc -b && vite build`) |
| Styling | One hand-written CSS file, custom properties |
| Charts | none — analytics rendered as markup |
| Test tooling | Playwright + Chromium, Lighthouse, Puppeteer |

No UI framework, no CSS framework, no client-side router, no state library.
The legacy pages are a single document each; navigation is full page loads.

---

## 4. Repository layout (frontend-relevant)

```
frontend/
├── index.html          generator page        (29 KB, 1 inline script block)
├── dashboard.html      six-view account area (44 KB, 25 KB inline JS)
├── pricing.html        pricing statement     (4.3 KB)
├── manual.html         working manual        (8 KB)
├── app.html            Vite entry for React  (1.3 KB)
├── src/
│   ├── main.tsx        React root
│   ├── App.tsx         page composition
│   ├── index.css       React-side tokens
│   └── components/
│       ├── chrome.tsx  Header / Nav / Footer / SkipLink
│       └── Link.tsx    anchor-or-button polymorphic link
└── dist/               build output, served at /assets/*
static/
├── css/style.css       all legacy styling, 21.5 KB
├── js/app.js           all generator logic, 795 lines
├── js/session.js       token refresh, IIFE
└── img/
    ├── heart.png       brand mark
    └── icons/*.svg     26 type icons, 64×64
```

---

## 5. Runtime architecture

### 5.1 Two shells, one nav

There are two independent implementations of the same site chrome.

| Shell | Entry | Served at | Capability |
|---|---|---|---|
| Legacy | `frontend/index.html` etc. | `/`, `/dashboard`, `/pricing`, `/manual` | Full product |
| React | `frontend/app.html` → `src/` | `/app` | Header, nav, footer only |

The React shell exists so shared chrome can be componentised once. It has not
yet absorbed any page body, so it currently renders a brand header, three nav
links and a one-line footer — no generator, no dashboard.

The two navs must be edited independently. They currently agree:
`Generator` → `/`, `Solutions` → `/#features`, `Dashboard` → `/dashboard`.

### 5.2 Request lifecycle

```
GET /dashboard
  └─ pages.py: dashboard_page()
       └─ _render_page("dashboard.html", active="dashboard")
            └─ replaces <!-- NAV --> with frontend/partials/nav.html

GET /static/js/session.js     ── Flask static handler, no processing
GET /assets/index-<hash>.js   ── pages.py:/assets/<path> and /frontend/<path>
GET /api/anything-unknown     ── catch-all: JSON 404
GET /anything-else            ── catch-all:
                                   file exists under frontend/? → send it
                                   otherwise                    → 404.html, 404
```

`_render_page` is the only way a legacy page is served. It reads the page,
injects the shared nav, and marks the active link with `aria-current="page"`.
There is no client-side router, so an unmatched path is a real 404; the old
fallback answered everything with `index.html` and status 200, which hid broken
links and made preview routes silently render the generator.

### 5.3 Script loading and globals

`index.html` loads exactly two scripts, in this order:

```html
<script src="/static/js/session.js"></script>
<script src="/static/js/app.js"></script>
```

The order is load-bearing. `session.js` defines the refresh machinery that
`app.js` calls when a session is stored; reversing the two means registration
and login succeed on the server but the client never schedules a token
refresh, so the user is silently logged out fifteen minutes later.

Neither file is a module. Both attach to global scope:

- `session.js` — one IIFE, exposing nothing deliberately; it patches
  `localStorage` conventions rather than exporting functions.
- `app.js` — `let state = {...}`, `const TYPES = [...]`, and 19 function
  declarations, all global. Markup calls them by name from inline `onclick`
  attributes (`onclick="closeModal('authModal')"`), so the HTML and the script
  are coupled through the global namespace.

`dashboard.html` inlines its own script block (25 KB, 14 functions) with no
external file at all.

### 5.4 State

State lives in three places, each with a different lifetime.

**Tier 1 — mutable module global (`app.js`).**

```js
let state = {
  type: "url",        // selected QR type
  isDynamic: false,   // static vs dynamic
  pattern: "square",  // module style
  eyeStyle: "square",
  fg: "#0A0A0A",
  bg: "#FFFFFF",
  gradient: "solid",  // solid | linear | radial
  frameText: "",
  frameColor: "#F5A623",
  logoB64: null,      // uploaded logo, data URL
  lastImage: null,    // last rendered PNG
  lastId: null,       // server id, set for dynamic QRs
  previewAbort: null  // AbortController for the in-flight preview
};
```

There is no reactivity. Every change is followed by a manual DOM write:
`renderForm()` rebuilds the form when `state.type` changes, `preview()`
rewrites `#qrImage`, `updatePreviewMeta()` updates the caption. Because state
is a single object, any handler can read or mutate any part of it.

**Tier 2 — `localStorage`.** Session material only:

| Key | Contents |
|---|---|
| `DR_token` | access token, 15 min lifetime |
| `DR_refresh` | refresh token, rotated on each renewal |
| `DR_user` | cached display identity |

**Tier 3 — URL query.** The dashboard mirrors its filter state into the query
string (`getUrlState` / `updateUrlState`), so a filtered view survives reload
and can be linked. The generator does not.

### 5.5 API communication

All calls are `fetch` against the same origin. There is no client abstraction
layer — no `api()` wrapper — so each call site repeats its own headers,
error handling and `Authorization` construction. Representative set:

| Call site | Endpoint | Purpose |
|---|---|---|
| `preview()` | `POST /api/preview` | render without persisting |
| `generate()` | `POST /api/generate` | create QR |
| `download()` path | `GET /api/download/<id>?format=` | server-side export |
| `submitAuth()` | `POST /api/login`, `/api/register` | session |
| dashboard `load()` | `GET /api/qrcodes` | list |
| dashboard `load()` | `GET /api/analytics/overview` | totals |
| dashboard `load()` | `GET /api/folders` | folders |
| dashboard `load()` | `GET /api/templates` | templates |

`load()` fans out four requests on every dashboard entry rather than composing
a single view endpoint. Four round trips, four failure modes, four loading
states that are not rendered independently.

Preview is debounced and abortable: each keystroke schedules `preview()` on a
timer, and the previous request is cancelled via `state.previewAbort` before a
new one starts. That is the one place the client does real concurrency
management.

### 5.6 Authentication and token lifecycle

Access tokens live 15 minutes. Rather than intercepting every `fetch`,
`session.js` renews in the background:

```
login / register
  └─ storeSession(response)
       ├─ localStorage.DR_token   = access token
       ├─ localStorage.DR_refresh = refresh token
       └─ schedule()              = setTimeout(13 min)

13 min elapse
  └─ refreshAccessToken()
       └─ POST /api/refresh { refresh_token }
            ├─ 200 → rotate both tokens, schedule again
            └─ 401 → clearSession(), require sign-in
```

13 minutes sits inside the 15-minute lifetime, so the token is replaced before
it can expire. Refresh tokens are rotated on every renewal: only the newest is
valid, so replaying an old one fails.

Consequence: any code path that establishes a session must call
`storeSession`, or the user keeps working until the access token dies and is
then dropped with no warning. That is why script order matters (§5.3).

### 5.7 Build pipeline

```
npm run build  →  tsc -b && vite build  →  frontend/dist/
```

`vite.config.ts`:

- **Entry** is `app.html` only. `index.html` is deliberately excluded so the
  React bundle can never overwrite the legacy generator page.
- **Output** `dist/`, served by Flask at `/assets/<path>`.
- **Proxy** `/api` → `http://localhost:5000` in dev only.
- **Vendor split** — `react` and `react-dom` in a separate chunk.
- **Sourcemaps on.**

The legacy pages need no build step. They ship as authored, which is why they
can be edited without a toolchain and also why they have no tree-shaking,
minification or bundling benefit.

---

## 6. Page layouts

### 6.1 `/` — Generator

The product page and the deepest surface in the app.

```
header.header
├── a.logo ................ DR + heart.png + QR
├── nav.nav ............... Generator · Solutions · Dashboard
└── .header-cta
    ├── #loginBtn ......... Log In
    ├── #registerBtn ...... Register — Free
    └── #ham .............. ☰  (mobile only)

section.hero
├── h1 .................... "The Most Advanced QR Code Generator with Logo"
├── .hero-actions
│   └── Create FREE QR → ... scrolls to #generator
└── preview mockup

section#generator
├── .gen-left
│   ├── #topCats ............ 5 category pills
│   ├── #typeGrid ........... 26 type tiles (JS)
│   ├── #dynamicToggle ...... static ↔ dynamic switch
│   ├── #generateBtn ........ ⚡ Generate QR Code
│   └── #resetBtn ........... Reset
└── .gen-right
    └── #previewCard
        ├── #previewType ..... active type label
        ├── #qrFrame
        │   ├── #qrImage ..... rendered QR
        │   ├── #qrLoading ... skeleton
        │   └── #qrNoPreview . empty state
        └── export row ....... PNG · SVG · PDF · ⬇ Download QR

#customTabs  (6 tabs)
├── #pane-pattern ... Square · Dots · Rounded · Gapped
├── #pane-eyes ...... Square Eyes · Circle Eyes · Rounded
├── #pane-colors .... Solid · Linear Gradient · Radial
│                     #fgColor #fgText  #bgColor #bgText
│                     3 palette chips
├── #pane-logo ...... #logoDropZone · #logoInput · #logoPreview
│                     #removeLogo
├── #pane-frame ..... text input, colour picker, 4 frame presets
└── #pane-templates . 4 presets · #saveTemplateBtn

section#features ....... "How to create a free QR code"
section.section-dark ... self-hosted positioning strip
footer ................. brand + link columns

#authModal ............. email, password, eye toggle, submit, switch mode
#twofaModal ............ 6-digit code, submit
#toast ................. transient notification
```

Layout is a two-column split that collapses to one column under the responsive
breakpoint; the preview column becomes a sticky panel on wide viewports.

### 6.2 `/dashboard` — one page, six views

```
header.header ......... logo · nav · #userEmail · #logout · ＋ Create New QR
aside.sidebar
├── #countBadge
└── 6 nav links, each data-view:
    qrs · analytics · folders · bulk · templates · settings
main.dash-main
├── #view-qrs
│   ├── #statsRow ... #sTotal #sScans #sDynamic #sStatic
│   ├── toolbar ..... #search, #filterType
│   ├── #qrList ..... rows, each with 6 actions
│   └── #empty ...... "No QR codes yet" + Create QR →
├── #view-analytics . #analyticsBody
├── #view-bulk ...... #bulkType, #bulkFile, #bulkBtn, #bulkOut
├── #view-folders ... #newFolder, #addFolder, #folderList
├── #view-templates . #tplList
└── #view-settings .. 2FA status + controls, cache controls
```

Only one view is visible; switching is a client-side class toggle with no
router and no history entry, except that filter state is written to the query
string.

### 6.3 `/pricing`

Single `section`. States that the product is free with no paid tier. Header CTA
is **Back →**; body CTA is **Start generating**; footer row is
**Generator → · API Docs · Dashboard**.

### 6.4 `/manual`

Single `section` rendering the working manual. Four CTAs: **Create QR → ·
View Markdown → · Health Check · Dashboard**.

### 6.5 `/app` — React shell

```
SkipLink ...... "Skip to main content"
Header
├── Link.brand ... DR + heart.png + QR
└── Nav .......... Generator · Solutions · Dashboard
Footer .......... one line
```

`Link.tsx` renders an `<a>` for external or same-page navigation and a
`<button>` when an `onClick` is supplied — one polymorphic component so every
navigational control behaves correctly under the keyboard.

---

## 7. Interaction flows

### 7.1 Selecting a QR type

```
click tile (renderTypeGrid, line 85 of app.js)
  └─ state.type = tile.dataset.type
       ├─ renderTypeGrid()  → moves .active
       └─ renderForm()      → rebuilds #formArea for that type's fields
```

`TYPES` is the single source of truth — id, label, category. The grid, the
category filter and the form all read from it, so adding a type is a one-line
change. Icons are resolved by convention: `static/img/icons/<id>.svg`.

### 7.2 Live preview

```
input event on #formArea
  └─ debounce(350 ms)
       └─ preview()
            ├─ abort previous request (state.previewAbort)
            ├─ buildContentForPreview()  → payload for this type
            └─ POST /api/preview
                 ├─ 200 → #qrImage.src = data URL
                 └─ error → toast()
```

Preview never persists anything; it is a rendering service. A QR only becomes
real at **Generate**.

### 7.3 Generating a QR

```
#generateBtn
  └─ generate()
       ├─ validateForm()      → per-field errors via showFieldError()
       ├─ collectData()       → payload from current type + styling
       └─ POST /api/generate
            ├─ static  → returns image, no id
            └─ dynamic → returns image + id + short code
                 └─ state.lastId = id
       └─ updatePreviewMeta()
```

Static QRs encode their payload directly and can never be changed after
printing. Dynamic QRs encode a short code; the payload lives server-side and is
served through `/r/<code>`, which is what makes post-print edits and scan
tracking possible.

### 7.4 Exporting

Two distinct paths:

```
state.lastId present (dynamic, server-side)
  └─ GET /api/download/<id>?format=png|svg|pdf
       Authorization: Bearer <DR_token>
       └─ Blob → object URL → <a download>

no lastId (static, client-side)
  └─ download(state.lastImage, filename)
       └─ data URL → anchor click
```

Same button, different mechanism depending on whether the QR exists on the
server. The dynamic path requires a valid session; the static path does not.

### 7.5 Registration and login

```
openAuth(mode)  → #authModal.open, fields swapped
  └─ #authSubmit → submitAuth()
       ├─ client validation (email format, password rules)
       ├─ POST /api/login   or   POST /api/register
       ├─ 200 → storeSession() → modal closes → updateAuthUI()
       └─ 4xx → inline field error, no toast
```

Registration may require email verification depending on server config, in
which case the response does not yield a session and the UI stays on the
modal.

### 7.6 Two-factor authentication

Enrolment, from dashboard → Settings:

```
#btn2faSetup  → POST /api/2fa/setup    → secret + otpauth QR in #twofaBox
#twofaCodeSetup → #btn2faVerify → POST /api/2fa/verify-setup
                                   ├─ 200 → 2FA on, reload status
                                   └─ 400 → wrong code

#btn2faDisable → POST /api/2fa/disable
```

Login with 2FA enabled:

```
POST /api/login → { requires_2fa: true }
  └─ #twofaModal opens
       └─ #twofaSubmit → POST /api/2fa/login-verify
            └─ 200 → storeSession()
```

### 7.7 Dashboard load

```
auth()  → no DR_token ? redirect to /?needAuth=1 :
  └─ load()
       ├─ GET /api/qrcodes           → renderQrs()
       ├─ GET /api/analytics/overview → stats
       ├─ GET /api/folders            → folders
       └─ GET /api/templates          → templates
```

Four parallel requests, none individually loading-stated. A failure in any one
leaves its panel empty with no distinction between "no data" and "request
failed".

### 7.8 Row actions

| Action | Handler | Effect |
|---|---|---|
| View | `openQr(id)` | `GET /api/qrcodes/<id>` → `#qrModal` |
| Edit | `editQr(id)` | populate `#editModal` (13 fields) → `PUT /api/qrcodes/<id>` |
| Duplicate | `duplicateQr(id)` | `POST /api/qrcodes/<id>/duplicate` |
| PNG / PDF | `downloadQr(id, fmt)` | `GET /api/download/<id>?format=` |
| Delete | `delQr(id)` | `DELETE /api/qrcodes/<id>`, confirm first |

### 7.9 Filtering

```
#search input / #filterType change
  └─ filtered()  → client-side filter over the already-loaded list
       └─ updateUrlState()  → ?q=&type=&view=
```

Filtering never hits the server; the full list is in memory. URL state is read
back on load by `getUrlState()`, which is what makes a filtered view
shareable.

### 7.10 Bulk generation

```
#bulkFile (CSV) + #bulkType
  └─ #bulkBtn → POST /api/qrcodes/bulk   (multipart FormData)
       ├─ button disabled, label → "Processing…"
       └─ response JSON pretty-printed into #bulkOut
            └─ count toasted on success
```

This is a single request, not a job queue: the button stays disabled for the
duration and the whole result arrives at once. It works for the documented
ceiling of 3,000 rows, but there is no progress reporting and no resume —
closing the tab loses the run. `GET /api/qrcodes/bulk/<job_id>` exists on the
server and is not called by the frontend.

### 7.11 Scanning a dynamic QR

```
GET /r/<code>
  └─ redirect.py
       ├─ look up code
       ├─ record scan (time, referrer, coarse geo)
       └─ 302 → destination
```

This is the only browser-facing route that leaves the SPA pattern, and the only
one served to end users rather than the operator.

---

## 8. Design system

### 8.1 Tokens

Defined once in `:root` in `static/css/style.css`; the React shell mirrors them
in `src/index.css`.

| Token | Value | Role |
|---|---|---|
| `--grid-white` | `#F8F9FA` | page background |
| `--grid-line` | `#E9ECEF` | hairlines, dividers |
| `--black` | `#0A0A0A` | primary text |
| `--black-2` | `#111111` | raised surfaces |
| `--black-3` | `#1A1A1A` | panels |
| `--accent` | `#F5A623` | the only accent |
| `--accent-2` | `#F7B84B` | hover |
| `--accent-3` | `#D4940A` | pressed |
| `--accent-glow` | `0 0 20px rgba(245,166,35,.5)` | focus and active glow |
| `--radius` | `18px` | cards, inputs |
| `--radius-lg` | `28px` | modals, hero panels |

Amber is the sole accent. Red is reserved for the heart in the wordmark and is
not a UI colour.

### 8.2 Button system

Five modifiers on one base `.btn`:

| Class | Appearance | Use |
|---|---|---|
| `.btn-primary` | amber fill, black text | the one committing action per region |
| `.btn-ghost` | transparent, bordered | secondary and destructive |
| `.btn-dark` | near-black fill | tertiary on light panels |
| `.btn-sm` | compact | header, table rows, modal footers |
| `.btn-loading` | disabled + spinner | in-flight submit |

Most buttons are real `<button>` elements. Marketing and cross-page CTAs are
`<a class="btn …">` so they remain links for middle-click and crawlers.

### 8.3 Motion

The wordmark heart spins on `rotateY` under `perspective: 400px`, guarded by
`prefers-reduced-motion`. Transitions use the token durations rather than
per-rule literals.

---

## 9. Button inventory

111 controls across the legacy pages, plus 5 links in the React shell.
76 are static `<button>` elements, 7 are `<a class="btn …">`, and 28 are
generated at runtime (26 type tiles, 2 preview actions).

### 9.1 Generator — 78

| Area | # | Control | Id / class | Effect |
|---|---|---|---|---|
| Header | 1 | Log In | `#loginBtn` | opens `#authModal` in login mode |
| | 2 | Register — Free | `#registerBtn` | opens `#authModal` in register mode |
| | 3 | ☰ | `#ham` | toggles mobile nav |
| Hero | 4 | Create FREE QR → | `.btn-primary` | scrolls to `#generator` |
| Categories | 5–9 | All 25+ · Popular · Business · Social · Utility | `.tab-pill` | filters `#typeGrid` |
| Type grid | 10–35 | 26 type tiles | `.type-btn` | sets `state.type`, rebuilds form |
| Actions | 36 | ⚡ Generate QR Code | `#generateBtn` | `POST /api/generate` |
| | 37 | Reset | `#resetBtn` | clears `state` and form |
| Customise tabs | 38 | Pattern | `#customTabs` | shows `#pane-pattern` |
| | 39 | Eyes | | shows `#pane-eyes` |
| | 40 | Colors | | shows `#pane-colors` |
| | 41 | Logo | | shows `#pane-logo` |
| | 42 | Frame | | shows `#pane-frame` |
| | 43 | Templates | | shows `#pane-templates` |
| Pattern | 44–47 | Square · Dots · Rounded · Gapped | `.opt-btn` | `state.pattern` |
| Eyes | 48–50 | Square Eyes · Circle Eyes · Rounded | `.opt-btn` | `state.eyeStyle` |
| Colors | 51–53 | Solid · Linear Gradient · Radial | `.opt-btn` | `state.gradient` |
| | 54–56 | Black/White · Black/Neon · Neon/Black | `.chip` | preset `fg`/`bg`/`gradient` |
| Logo | 57 | ✕ Remove Logo | `#removeLogo` | clears `state.logoB64` |
| Frame | 58–61 | SCAN ME · DRQR · WIFI CONNECT · OPEN MENU | `.chip` | `state.frameText` |
| Templates | 62–65 | Neon Pop · Mono Black · Grid White · Neon Night | `.opt-btn` | applies a saved style |
| | 66 | Save as Template | `#saveTemplateBtn` | `POST /api/templates` |
| Export | 67 | PNG | `.btn-ghost` | `GET /api/download` or client save |
| | 68 | SVG | `.btn-ghost` | format=svg |
| | 69 | PDF | `.btn-ghost` | format=pdf |
| | 70 | ⬇ Download QR | `#downloadBtn` | current format |
| Bottom CTA | 71 | Create FREE QR → | `.btn-primary` | scrolls to `#generator` |
| Auth modal | 72 | ✕ | `.btn-ghost` | `closeModal('authModal')` |
| | 73 | 👁 | `#togglePass` | reveal password |
| | 74 | Continue → | `#authSubmit` | `POST /api/login` or `/register` |
| 2FA modal | 75 | ✕ | `.btn-ghost` | `closeModal('twofaModal')` |
| | 76 | Verify → | `#twofaSubmit` | `POST /api/2fa/login-verify` |
| Preview (runtime) | 77 | download | `.btn-primary.btn-sm` | `download(state.lastImage, name)` |
| | 78 | Dashboard | `.btn-ghost.btn-sm` | `location.href = '/dashboard'` |

The logo pane also contains a clickable dropzone (`#logoDropZone`) and a hidden
file input (`#logoInput`) — interactive, but not `<button>` elements.

### 9.2 Dashboard — 24

| Area | # | Control | Id / class | Effect |
|---|---|---|---|---|
| Header | 1 | Log Out | `#logout` | `POST /api/logout`, clear session, redirect |
| | 2 | ＋ Create New QR | `.btn-primary` | `location.href = '/'` |
| QRs view | 3 | Create QR → | `.btn-primary` | empty state, `location.href = '/'` |
| | 4–9 | View · Edit · Duplicate · PNG · PDF · Delete | `.btn-sm` | per-row actions (§7.8) |
| Bulk | 10 | Generate Bulk → | `#bulkBtn` | `POST /api/qrcodes/bulk` |
| Folders | 11 | Add | `#addFolder` | `POST /api/folders` |
| Settings | 12 | Setup 2FA → | `#btn2faSetup` | `POST /api/2fa/setup` |
| | 13 | Disable 2FA | `#btn2faDisable` | `POST /api/2fa/disable` |
| | 14 | Verify & Enable | `#btn2faVerify` | `POST /api/2fa/verify-setup` |
| | 15 | Clear Local Cache | `.btn-ghost` | `localStorage.clear()` + toast |
| | 16 | Reload Data | `.btn-dark` | re-runs `load()` |
| | 17 | Reset DB Help | `.btn-ghost` | confirm, then a toast telling the operator to delete `data/DR.db` — it does not touch the database itself |
| QR modal | 18 | ✕ | `.btn-ghost` | `closeModal('qrModal')` |
| | 19 | ⬇ PNG | `.btn-primary` | `downloadQr(id,'png')` |
| | 20 | PDF | `.btn-ghost` | `downloadQr(id,'pdf')` |
| | 21 | Close | `.btn-ghost` | `closeModal('qrModal')` |
| Edit modal | 22 | ✕ | `.btn-ghost` | `closeModal('editModal')` |
| | 23 | 💾 Save Changes | `#editSave` | `PUT /api/qrcodes/<id>` |
| | 24 | Cancel | `.btn-ghost` | discard |

Plus two `<select>` controls (`#filterType`, `#bulkType`), a text input
(`#search`), and six sidebar links — interactive, not buttons.

### 9.3 Pricing — 5

| Control | Kind | Target |
|---|---|---|
| Back → | button | `/` |
| Start generating | button | `/` |
| Generator → | `a.btn-primary` | `/` |
| Dashboard | `a.btn-ghost` | `/dashboard` |

### 9.4 Manual — 4

| Control | Kind | Target |
|---|---|---|
| Create QR → | `a.btn-primary` | `/` |
| View Markdown → | `a.btn-primary` | `/MANUAL.md` |
| Health Check | `a.btn-ghost` | `/api/health` |
| Dashboard | `a.btn-ghost` | `/dashboard` |

### 9.5 Runtime-generated (included above, not additional)

The 26 type tiles are rows 10–35 and the two preview actions are rows 77–78.
They are listed here by construction so the generator's DOM-building code is
documented in one place:

| Control | Where | Handler |
|---|---|---|
| 26 type tiles | `renderTypeGrid()`, `app.js:85` | sets `state.type` |
| download | preview template, `app.js:351` | `download(state.lastImage, name)` |
| go to dashboard | preview template, `app.js:352` | `location.href = '/dashboard'` |

### 9.6 React shell — 5 links

`SkipLink` (skip to main), brand link, and the three nav items. All rendered by
`Link.tsx`.

---

## 10. Architecture assessment

### Strengths

- **One data source for QR types.** `TYPES` drives the grid, the filter and the
  form. Adding a type is one line plus one SVG.
- **Preview is properly debounced and abortable.** The previous request is
  cancelled rather than raced, so a fast typist cannot flash a stale code.
- **Token refresh is centralised and rotated.** No `fetch` call site needs to
  know about expiry, and replaying an old refresh token fails.
- **URL-synced dashboard filters.** Filter state is linkable and survives
  reload without a router.
- **The React entry is isolated.** `app.html` as the sole Vite input means the
  build cannot overwrite the legacy generator.

### Risks and debt

**No module system.** 795 lines of global functions in `app.js` plus 25 KB of
inline script in `dashboard.html`. Inline `onclick` attributes couple markup to
globals, so nothing can be tree-shaken, unit-tested in isolation, or safely
renamed. The inline dashboard script is also not separately cacheable: every
dashboard visit re-downloads 25 KB that never changes between deploys.

**Duplicated chrome, now two copies.** The four legacy pages carry a
`<!-- NAV -->` marker filled from `frontend/partials/nav.html`; `chrome.tsx`
keeps its own `Nav()` because the rebuild tests require that component. Two
definitions of a three-link nav remain, and nothing enforces that they agree.

**Two export mechanisms behind one button.** Server-side for dynamic QRs,
client-side for static. Correct, but the difference is invisible in the UI and
only documented here.

### Fixed in the hardening pass

**One failed dashboard request blanked the rest of the page.** `load()` now
fans out with `Promise.allSettled`; every panel renders its own static
skeleton, an empty state, and an error with a working Retry.

**Silent 200 fallback.** An unmatched path returns `frontend/404.html` with
status 404, and an unmatched `/api/*` path returns JSON 404.

**Production sourcemaps.** `vite.config.ts` sets `sourcemap: false`.

**`/api-docs` rendered blank.** The Swagger UI page fetched its CSS and JS from
unpkg, which the app's own Content-Security-Policy blocks. The route now
renders the endpoint index from `build_spec()` on the server, with no external
assets, and the manual links to it.

**Two export mechanisms behind one button.** Server-side for dynamic QRs,
client-side for static. Correct, but the difference is invisible in the UI and
only documented here.

---

## 11. Appendix — route and endpoint tables

### Page routes

| Route | Handler | Serves |
|---|---|---|
| `/` | `pages.index` | `frontend/index.html` |
| `/app` | `pages.react_app` | `frontend/app.html` |
| `/dashboard` | `pages.dashboard_page` | `frontend/dashboard.html` + nav |
| `/pricing` | `pages.pricing_page` | `frontend/pricing.html` + nav |
| `/manual` | `pages.manual_page` | `frontend/manual.html` + nav |
| `/MANUAL.md` | `pages.manual_md` | raw markdown |
| `/api-docs` | `pages.api_docs_page` | API reference from `build_spec()` |
| `/assets/<path>` | `pages.dist_assets` | Vite build output |
| `/frontend/<path>` | `pages.frontend_static` | direct file |
| `/<path>` | `pages.catch_all` | file or `404.html` (status 404) |

### API endpoints

35 distinct endpoints; most are published twice, plain and under `/api/v1`.

| Group | Endpoints |
|---|---|
| Auth (13) | `register` · `login` · `verify-email` · `resend-verification` · `refresh` · `logout` · `forgot-password` · `reset-password` · `2fa/setup` · `2fa/verify-setup` · `2fa/disable` · `2fa/login-verify` · `me` |
| QR (11) | `generate` · `preview` · `qrcodes` (list/create) · `qrcodes/<id>` (get/put/delete) · `qrcodes/bulk` · `qrcodes/bulk/<job>` · `download/<id>` · `qrcodes/<id>/duplicate` · `health` · `qrcodes/<id>/analytics` |
| Analytics (1) | `analytics/overview` |
| Meta (2) | `folders` · `templates` |
| Reviews (5) | `reviews` (get/post) · `reviews/summary` · `reviews/flagged` · `reviews/export` |
| Docs (1) | `openapi.json`, `docs` |
| Ops (1) | `metrics` |
| Redirect (1) | `/r/<code>` |

### Browser storage

| Key | Lifetime | Cleared by |
|---|---|---|
| `DR_token` | 15 min | refresh failure, logout, Clear Local Cache |
| `DR_refresh` | server-defined, rotated | refresh failure, logout, Clear Local Cache |
| `DR_user` | until logout | logout, Clear Local Cache |

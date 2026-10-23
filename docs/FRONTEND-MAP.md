# Frontend map

Generated from the source, not from memory. Two layout shells ship in this
repo: the legacy HTML pages served at `/` and the React shell served at
`/app`.

## Routes

| Route | File | Purpose |
|---|---|---|
| `/` | `frontend/index.html` | Generator — the main product page |
| `/dashboard` | `frontend/dashboard.html` | Six-view account area |
| `/pricing` | `frontend/pricing.html` | Pricing statement |
| `/manual` | `frontend/manual.html` | Working manual |
| `/MANUAL.md` | `MANUAL.md` | Manual source, served raw |
| `/api-docs` | — | API reference |
| `/app` | `frontend/app.html` → `frontend/src/` | React shell |
| `/assets/<path>` | `frontend/dist/assets/` | Built React bundle |
| `/<path>` | `frontend/<path>` | Static passthrough, else SPA fallback to `index.html` |

## `/` — Generator

```
header
├── brand (DR + heart + QR)
├── nav ............ Generator · Solutions · Dashboard
└── actions
    ├── Log In              #loginBtn
    ├── Register — Free     #registerBtn
    └── ☰ hamburger         #ham          (mobile)

section.hero
├── headline + subcopy
└── Create FREE QR →                      (scrolls to #generator)

section#generator
├── left column
│   ├── category filter ... All 25+ · Popular · Business · Social · Utility
│   ├── type grid ......... #typeGrid  (26 tiles, built in app.js)
│   ├── dynamic toggle .... #dynamicToggle
│   ├── Generate QR Code .. #generateBtn
│   └── Reset ............. #resetBtn
└── right column (#previewCard)
    ├── #qrImage / #qrLoading / #qrNoPreview
    └── export ............ PNG · SVG · PDF · ⬇ Download QR

customisation panel (#customTabs)
├── Pattern ... Square · Dots · Rounded · Gapped
├── Eyes ...... Square Eyes · Circle Eyes · Rounded
├── Colors .... Solid · Linear Gradient · Radial
│               Black/White · Black/Neon · Neon/Black
├── Logo ...... dropzone (#logoDropZone) · Upload (#logoInput) · Remove
├── Frame ..... SCAN ME · DRQR · WIFI CONNECT · OPEN MENU
└── Templates . 4 presets · Save as Template

section#features
├── "How to create a free QR code"
└── Create Free QR →

section.section-dark
└── Self-hosted · SQLite or PostgreSQL · No external tracking

footer
├── brand + tagline
└── link columns

modals
├── #authModal ... email · password · eye toggle · Continue → · switch login/register
└── #twofaModal .. 6-digit code · Verify →
```

## `/dashboard` — six views, one page

```
header
├── nav ............ Generator · Solutions · Dashboard
├── Log Out ....... #logout
└── ＋ Create New QR

aside.sidebar            main.dash-main
├── QRs ................ #statsRow, #search, #filterType, #qrList
├── Analytics .......... #analyticsBody
├── Folders ............ #newFolder, #addFolder, #folderList
├── Bulk ............... #bulkType, #bulkFile, #bulkBtn, #bulkOut
├── Templates .......... #tplList
└── Settings ........... #twofaStatus, #btn2faSetup, #btn2faDisable,
                         #twofaBox, #twofaQR, #twofaSecret, #btn2faVerify,
                         Clear Local Cache
```

Views are switched client-side by `data-view` on the sidebar links; only one
panel is visible at a time. State is URL-synced.

Row actions in the QRs list, per QR: **View · ✎ Edit · ⎘ Duplicate · PNG ·
PDF · Delete**. Bulk actions and the edit form live in two modals:

```
#qrModal    ✕ · ⬇ PNG · PDF · Close
#editModal  name · type · content · colours · pattern · eyes · frame ·
            password · scan limit · expiry · ✕ · Save Changes · Cancel
```

## `/pricing`

Single `section` — "Free, and there is no paid tier". Header carries
**Back →**. Footer carries **Generator → · API Docs · Dashboard**. Body has
**Start generating**.

## `/manual`

Single `section` — "DRQR — Working Manual". Header CTAs: **Create QR → ·
View Markdown → · Health Check · Dashboard**.

## `/app` — React shell

`frontend/src/` renders header, nav and footer only; there is no generator in
this shell yet.

```
SkipLink ....... "Skip to main content"
Header
├── brand (DR + heart + QR)
└── Nav ......... Generator · Solutions · Dashboard
Footer .......... one line
```

The React nav and the legacy nav must be changed together — they are two
separate implementations of the same chrome.

## Button inventory

107 controls across the legacy pages, plus 5 links in the React shell.

### Generator — 76

| Area | Count | Controls |
|---|---|---|
| Header | 3 | Log In, Register — Free, ☰ |
| Hero | 1 | Create FREE QR → |
| Category filter | 5 | All 25+, Popular, Business, Social, Utility |
| Type grid | 26 | One tile per QR type, built in `app.js` |
| Form actions | 2 | ⚡ Generate QR Code, Reset |
| Customise tabs | 6 | Pattern, Eyes, Colors, Logo, Frame, Templates |
| Pattern | 4 | Square, Dots, Rounded, Gapped |
| Eyes | 3 | Square Eyes, Circle Eyes, Rounded |
| Colors | 6 | Solid, Linear Gradient, Radial + 3 palette chips |
| Logo | 1 | ✕ Remove Logo (plus a dropzone and a file input) |
| Frame | 4 | SCAN ME, DRQR, WIFI CONNECT, OPEN MENU |
| Templates | 5 | 4 presets, Save as Template |
| Export | 4 | PNG, SVG, PDF, ⬇ Download QR |
| Bottom CTA | 1 | Create FREE QR → |
| Auth modal | 3 | ✕, 👁 toggle, Continue → |
| 2FA modal | 2 | ✕, Verify → |

### Dashboard — 22

| Area | Count | Controls |
|---|---|---|
| Header | 2 | Log Out, ＋ Create New QR |
| QRs view | 7 | Create QR → (empty state) + View, Edit, Duplicate, PNG, PDF, Delete per row |
| Bulk view | 1 | Generate Bulk → |
| Folders view | 1 | Add |
| Settings | 4 | Setup 2FA →, Disable 2FA, Verify & Enable, Clear Local Cache |
| QR modal | 4 | ✕, ⬇ PNG, PDF, Close |
| Edit modal | 3 | ✕, Save Changes, Cancel |

### Pricing — 5

Back →, Start generating, Generator →, API Docs, Dashboard.

### Manual — 4

Create QR →, View Markdown →, Health Check, Dashboard.

### Generated at runtime — 2

In `app.js`, inside the preview panel: **download** and **go to dashboard**.

### Styles

`.btn-primary`, `.btn-ghost`, `.btn-dark`, `.btn-sm`, `.btn-loading`.
Every button is a `<button>` except the marketing/CTA links, which are
`<a class="btn …">`.

## Notes

Two shell implementations of the same chrome exist, so the nav is duplicated
and must be edited in both places.

`/manual`, `/MANUAL.md` and `/api-docs` are still live routes, and
`pricing.html` still links to `/api-docs`, even though neither appears in the
nav.

Six anchors across `dashboard.html`, `pricing.html` and `manual.html` are
formatted with `</a` and `>` split across two lines. Valid HTML, but `grep
"</a>"` misses them and naive tag counters report them as unclosed.

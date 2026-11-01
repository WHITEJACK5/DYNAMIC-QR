# Changelog

All notable changes to DRQR, in the spirit of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 2026-10-23 — Dark, border-first redesign and hardening

### Changed

- **One accent, used deliberately.** Lime (`#D9F26B`) marks the single primary
  action in a region, links, the active nav item, and the focus ring. It is not
  used for decoration. The QR code is the product; a second accent would compete
  with it, so one accent keeps attention on the code and the next step.
- **Borders and spacing instead of shadows.** Depth comes from `1px` borders
  and a three-step surface ramp (`--bg` → `--surface` → `--surface-2`). There are
  no gradients, glows, backdrop blur, or hover transforms. Shadows read as a
  dashboard template; borders read as a tool, stay crisp at every zoom level,
  and survive high-contrast mode.
- **Type split by job.** Space Grotesk for headings (tight and geometric at
  large sizes), Inter for body copy (tall x-height, designed for interface
  text), and JetBrains Mono for labels, QR type names, and metadata (aligned
  figures, visibly "data" rather than prose). All three are self-hosted
  variable woff2 files in `static/fonts/`, so there are no external font
  requests and the app renders the same offline.
- **The QR preview sits on a light panel.** Codes render on `#ECEBE8` with dark
  modules while the surrounding UI stays dark. The scanner-facing surface does
  not inherit the app's theme.
- **Presets that scan.** `Ink/White`, `Ink/Lime`, and `Ink/Paper` replace the
  inverted `Neon/Black` preset, which produced light-on-dark codes.

### Added

- **A print proof beside the live preview.** The supplied field illustration
  fills the empty desktop column on a paper panel, with a short
  print/scan/update caption. It uses the existing ink and paper tokens, and it
  is hidden below `1024px`, where the preview takes the full width.
- **A glowing footer sign-off.** The site footer line carries a soft lime halo
  — the one deliberate exception to the no-glow rule, requested after the
  first visual pass.

### Fixed

- The dashboard loads its four panels in parallel with `Promise.allSettled`.
  Each panel has its own skeleton, empty state, and error state with a working
  Retry, so one failed request no longer blanks the page.
- Unknown URLs return a styled `404.html` with status 404, and unmatched
  `/api/*` paths return JSON 404. The previous catch-all answered every mistyped
  path with `index.html` and status 200.
- The nav lives once in `frontend/partials/nav.html` and is injected into all
  four legacy pages; five hand-maintained copies became one plus the React
  component.
- `sourcemap` is off in the production Vite build.
- "Clear Local Cache" preserves `DR_token`, `DR_refresh`, and `DR_user`, so it
  no longer logs the user out silently. The fake "Reset DB Help" control is now
  non-destructive, honest instructions.
- `/api-docs` rendered blank because its Swagger UI assets were blocked by the
  app's own Content-Security-Policy. It is now a server-rendered endpoint
  reference with no external requests.
- **Eyes now follow the Eyes control.** Finder patterns have their own renderer
  path instead of inheriting the data pattern, so every Pattern × Eyes
  combination and every template decodes in OpenCV.
- **Templates stay in sync with the customizer.** Choosing a template updates
  Pattern, Eyes, Colors, and the active preset; manual changes clear the
  template highlight. Sharp is black ink with rounded eyes, not a near-duplicate
  of Mono.
- **Addresses no longer preload into QR forms.** Auth and Email QR inputs ignore
  saved browser addresses unless the user typed them.
- **Security fields stay tidy.** Password and expiry use a two-column block with
  a full-width date field and a visible native calendar control in dark mode.
- **Live links use the reachable base URL.** Dynamic QRs encode the effective
  `BASE_URL` (including LAN addresses), not localhost, and the success bar shows
  the full link.
- **Redirect pages contain scanned content.** Password and non-http destination
  pages use the dark theme, escape scanned values, and no longer expose raw
  content; the health labels now match the Ink / Paper / Lime palette.
- The preview footer's mojibake corner glyph is now a real `©`, so the
  `© 2026 DRQR • Personal use • Local DB` line reads correctly everywhere.

/**
 * Shared site chrome (Phase 8).
 *
 * The directive: "Component-ize the shared header/nav/footer that is
 * currently copy-pasted across every page."
 *
 * These three components are the single source of truth for the site chrome.
 * Every page composes them, so a change to the nav happens once instead of
 * five times — which is the actual defect the directive is describing.
 *
 * Accessibility (Phase 8b) is built in rather than bolted on:
 *   - semantic <header>/<nav>/<footer> landmarks
 *   - aria-label on the nav so screen readers can jump to it
 *   - a skip link as the first focusable element
 *   - keyboard-focusable links with visible focus styles
 */
import { Link } from './Link'

export function SkipLink() {
  return (
    <a href="#main" className="skip-link">
      Skip to main content
    </a>
  )
}

export function Header() {
  return (
    <header className="site-header">
      <SkipLink />
      <Link href="/" className="brand" aria-label="DRQR home">
        DR
        <img
          src="/static/img/heart.png"
          alt=""
          className="brand-heart"
          width={20}
          height={20}
        />
        <span className="amp">QR</span>
      </Link>
      <Nav />
    </header>
  )
}

export function Nav() {
  return (
    <nav aria-label="Primary">
      <ul className="nav-list">
        <li>
          <Link href="/">Generator</Link>
        </li>
        <li>
          <Link href="/#features">Solutions</Link>
        </li>
        <li>
          <Link href="/dashboard">Dashboard</Link>
        </li>
      </ul>
    </nav>
  )
}

export function Footer() {
  return (
    <footer className="site-footer">
      <p>DRQR — self-hosted QR generation. Your data never leaves this machine.</p>
    </footer>
  )
}

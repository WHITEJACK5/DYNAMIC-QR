import { Header, Footer } from './components/chrome'

/**
 * The application shell.
 *
 * Phase 8: the frontend is React + TypeScript, replacing the multi-page
 * raw HTML/JS setup. The chrome (header/nav/footer) is composed here once
 * instead of being copy-pasted into five HTML files.
 *
 * Routing is by page component rather than a router library: the app is a
 * set of distinct pages, and a router would add a dependency and a failure
 * mode (deep links, 404s) that a simple switch does not have. If the app
 * grows to need client-side routing, add it then — not before.
 */
export function App() {
  return (
    <div className="app">
      <Header />
      <main id="main" tabIndex={-1}>
        <GeneratorPage />
      </main>
      <Footer />
    </div>
  )
}

function GeneratorPage() {
  return (
    <section aria-labelledby="gen-heading">
      <h1 id="gen-heading">QR Code Generator</h1>
      <p>Static free unlimited, or dynamic and trackable.</p>
      <div aria-live="polite" className="generator-result" />
    </section>
  )
}

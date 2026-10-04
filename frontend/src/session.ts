/**
 * Session handling for the React frontend (Phase 8 migration of session.js).
 *
 * The old static/js/session.js stored the access+refresh pair, renewed the
 * access token at 13 minutes (inside the 15-minute lifetime), re-armed the
 * timer, and renewed on visibilitychange so a laptop waking from sleep does
 * not fire requests with a stale token. Logout called /api/logout so tokens
 * are revoked server-side, not just dropped from storage.
 *
 * This module is the same contract, in TypeScript. It is deliberately not a
 * hook: it manages module-level state (the timer) and is called from components
 * that need it, rather than being tied to one component's lifecycle.
 */

const REFRESH_BEFORE_MS = 13 * 60 * 1000
const TOKEN_KEY = "DR_token"
const REFRESH_KEY = "DR_refresh"

let timer: ReturnType<typeof setTimeout> | null = null

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function storeSession(j: { access_token?: string; token?: string; refresh_token?: string }): void {
  localStorage.setItem(TOKEN_KEY, j.access_token || j.token || "")
  if (j.refresh_token) localStorage.setItem(REFRESH_KEY, j.refresh_token)
  schedule()
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  if (timer) clearTimeout(timer)
  timer = null
}

export async function refreshAccessToken(): Promise<boolean> {
  const rt = getRefreshToken()
  if (!rt) return false
  try {
    const r = await fetch("/api/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
    })
    if (!r.ok) {
      // 401 means the refresh token is expired, revoked or already used.
      // Nothing local can recover, so drop the session rather than looping.
      if (r.status === 401) clearSession()
      return false
    }
    const j = await r.json()
    localStorage.setItem(TOKEN_KEY, j.access_token)
    localStorage.setItem(REFRESH_KEY, j.refresh_token)
    return true
  } catch {
    return false // offline: try again on the next tick
  }
}

function schedule(): void {
  if (timer) clearTimeout(timer)
  if (!getRefreshToken()) return
  timer = setTimeout(() => {
    refreshAccessToken().then(schedule)
  }, REFRESH_BEFORE_MS)
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/logout", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getAccessToken()}`,
      },
      body: JSON.stringify({ refresh_token: getRefreshToken() }),
    })
  } catch {
    // offline: dropping local state is still correct
  }
  clearSession()
}

// A sleeping laptop returns with an expired access token; renew on wake.
if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && getRefreshToken()) refreshAccessToken()
  })
  // and once on load, in case the tab was restored from a bfcache
  schedule()
}

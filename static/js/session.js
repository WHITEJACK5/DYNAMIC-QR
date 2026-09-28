// Session handling for short-lived access tokens (Phase 4c).
//
// Access tokens now expire after 15 minutes instead of 7 days. Without
// this, a signed-in user would be logged out every 15 minutes. Instead of
// wrapping every fetch call site, tokens are renewed in the background a
// little before they expire, so the value read from localStorage is always
// fresh. A refresh token is rotated on each renewal (see /api/refresh), so
// only the newest one is ever usable.
(function () {
  const REFRESH_BEFORE_MS = 13 * 60 * 1000; // 13 min, inside the 15 min lifetime
  let timer = null;

  function storeSession(j) {
    localStorage.setItem('nare_token', j.access_token || j.token);
    if (j.refresh_token) localStorage.setItem('nare_refresh', j.refresh_token);
    schedule();
  }

  function clearSession() {
    localStorage.removeItem('nare_token');
    localStorage.removeItem('nare_refresh');
    localStorage.removeItem('nare_user');
  }

  async function refreshAccessToken() {
    const rt = localStorage.getItem('nare_refresh');
    if (!rt) return false;
    try {
      const r = await fetch(`${API}/api/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt })
      });
      if (!r.ok) {
        // 401 means the refresh token is expired, revoked or already used.
        // Nothing local can recover from that, so drop the session and make
        // the user sign in again rather than looping on 401s.
        if (r.status === 401) clearSession();
        return false;
      }
      const j = await r.json();
      localStorage.setItem('nare_token', j.access_token);
      localStorage.setItem('nare_refresh', j.refresh_token);
      return true;
    } catch (e) {
      return false; // offline: try again on the next tick
    }
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    if (!localStorage.getItem('nare_refresh')) return;
    timer = setTimeout(async function () {
      await refreshAccessToken();
      schedule();
    }, REFRESH_BEFORE_MS);
  }

  // Laptop asleep for an hour returns a stale token; renew on wake.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && localStorage.getItem('nare_refresh')) refreshAccessToken();
  });

  async function logout() {
    // Tell the server so the tokens are actually revoked, not just dropped.
    try {
      await fetch(`${API}/api/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('nare_token')}`
        },
        body: JSON.stringify({ refresh_token: localStorage.getItem('nare_refresh') })
      });
    } catch (e) { /* offline: dropping local state is still correct */ }
    clearSession();
  }

  window.NareSession = { storeSession, clearSession, refreshAccessToken, logout, schedule };
  schedule();
})();

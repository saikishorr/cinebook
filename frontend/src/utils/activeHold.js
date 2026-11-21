// The seat hold this browser tab is checking out, kept in sessionStorage so a refresh or a
// trip back to the seat map does not lose it. Every access is guarded: storage can be blocked.
const KEY = 'cinebook_hold'

export function readActiveHold() {
  try {
    const hold = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    // Ignore a hold whose expiry time has already passed.
    if (hold?.expires_at && new Date(hold.expires_at).getTime() <= Date.now()) {
      sessionStorage.removeItem(KEY)
      return null
    }
    return hold
  } catch {
    return null
  }
}

export function saveActiveHold(hold) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({
      hold_id: hold.hold_id,
      show_id: hold.show_id,
      expires_at: hold.expires_at,
    }))
  } catch {
    // Storage unavailable: checkout still works through the URL.
  }
}

export function clearActiveHold() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

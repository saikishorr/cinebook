const BASE_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

// The signed-in customer's session (see src/auth.jsx). Kept in localStorage so it survives a restart;
// the server ends it after 30 days or at sign-out.
const USER_KEY = 'cinebook_user'

export function userSession() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null') } catch { return null }
}

export function saveUserSession(session) {
  try {
    if (session) localStorage.setItem(USER_KEY, JSON.stringify(session))
    else localStorage.removeItem(USER_KEY)
  } catch { /* storage blocked: the customer signs in again next visit */ }
}

async function request(path, options = {}) {
  const session = userSession()
  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        // Customer token on every call; admin calls pass their own Authorization header, which wins.
        ...(session?.token ? { Authorization: `Bearer ${session.token}` } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new Error('The CineBook backend could not be reached. Please check that it is running.')
  }
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }

  if (!response.ok) {
    const detail = typeof data?.detail === 'string'
      ? data.detail
      : Array.isArray(data?.detail)
        ? data.detail.map(item => item.msg).join(', ')
        : `Request failed (${response.status}).`
    const error = new Error(detail)
    error.status = response.status
    throw error
  }
  return data
}

function query(params = {}) {
  const pairs = Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  return pairs.length ? `?${new URLSearchParams(pairs)}` : ''
}

export const getMovies = (params) => request(`/movies${query(params)}`)
export const getMovie = movieId => request(`/movies/${encodeURIComponent(movieId)}`)
export const getMovieShows = (movieId, params) => request(`/movies/${encodeURIComponent(movieId)}/shows${query(params)}`)
export const getMovieShowDates = movieId => request(`/movies/${encodeURIComponent(movieId)}/show-dates`)

// Real Pune cinemas (names and locations); their showtimes are CineBook demo data.
export const getCinemas = params => request(`/cinemas${query(params)}`)
export const getCinemaAreas = () => request('/cinemas/areas')
export const getCinema = cinemaId => request(`/cinemas/${encodeURIComponent(cinemaId)}`)
export const getCinemaShows = (cinemaId, date) => request(`/cinemas/${encodeURIComponent(cinemaId)}/shows${query({ date })}`)
export const getShow = showId => request(`/shows/${encodeURIComponent(showId)}`)
export const getSeats = showId => request(`/shows/${encodeURIComponent(showId)}/seats`)
export const createHold = (showId, seatIds) => request(`/shows/${encodeURIComponent(showId)}/holds`, { method: 'POST', body: JSON.stringify({ seat_ids: seatIds }) })
export const getHold = holdId => request(`/holds/${encodeURIComponent(holdId)}`)
export const cancelHold = holdId => request(`/holds/${encodeURIComponent(holdId)}`, { method: 'DELETE' })
export const createBooking = (holdId, { fullName, email, phone, smsConsent = false }) => request('/bookings', {
  method: 'POST',
  body: JSON.stringify({ hold_id: holdId, full_name: fullName, email, phone, sms_consent: smsConsent }),
})
export const getBooking = bookingRef => request(`/bookings/${encodeURIComponent(bookingRef)}`)

// Phase 2: chat links and the Demo Phone inbox
export const getChatLink = code => request(`/chat-links/${encodeURIComponent(code)}`)
export const getDemoInbox = (phone, accessCode) => request('/demo-phone/inbox', {
  method: 'POST',
  body: JSON.stringify({ phone, access_code: accessCode }),
})

// Phase 3: Help & info (the same content the chat assistant answers from)
export const getHelp = () => request('/help')

// Phase 3: the chat assistant
export const getChatMessages = code => request(`/chat-links/${encodeURIComponent(code)}/messages`)
export const sendChatMessage = (code, message) => request(`/chat-links/${encodeURIComponent(code)}/messages`, {
  method: 'POST',
  body: JSON.stringify({ message }),
})

// ---------------------------------------------------------------- Film admin (signed-in staff only)
// The session token lives in sessionStorage: it ends with the browser tab, and the server expires it after 12 hours.
const ADMIN_KEY = 'cinebook_admin'

export function adminSession() {
  try { return JSON.parse(sessionStorage.getItem(ADMIN_KEY) || 'null') } catch { return null }
}

function saveAdminSession(session) {
  try {
    if (session) sessionStorage.setItem(ADMIN_KEY, JSON.stringify(session))
    else sessionStorage.removeItem(ADMIN_KEY)
  } catch { /* storage blocked: the admin must sign in again after a refresh */ }
}

async function adminRequest(path, options = {}) {
  const session = adminSession()
  try {
    return await request(`/admin${path}`, {
      ...options,
      cache: 'no-store',
      headers: { ...(session ? { Authorization: `Bearer ${session.token}` } : {}), ...options.headers },
    })
  } catch (error) {
    if (error.status === 401) saveAdminSession(null)   // expired or revoked: back to the sign-in form
    throw error
  }
}

export async function adminLogin(username, password) {
  const session = await request('/admin/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  saveAdminSession(session)
  return session
}

// Keep the stored staff session in step with the server (role and permissions can change).
export function updateAdminSession(fields) {
  const session = adminSession()
  if (session) saveAdminSession({ ...session, ...fields })
  return adminSession()
}

export async function adminLogout() {
  try { await adminRequest('/logout', { method: 'POST' }) } finally { saveAdminSession(null) }
}

export const adminMovies = () => adminRequest('/movies')
export const adminSetActive = (movieId, isActive) => adminRequest(`/movies/${encodeURIComponent(movieId)}`, {
  method: 'PATCH', body: JSON.stringify({ is_active: isActive }),
})
export const adminSearchTmdb = q => adminRequest(`/tmdb/search?${new URLSearchParams({ q })}`)
export const adminAddMovie = film => adminRequest('/movies', { method: 'POST', body: JSON.stringify(film) })
export const adminExport = () => adminRequest('/movies/export')

// ---------------------------------------------------------------- Customer accounts
export const registerAccount = details => request('/auth/register', { method: 'POST', body: JSON.stringify(details) })
export const signInAccount = (email, password) => request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
export const signOutAccount = () => request('/auth/logout', { method: 'POST' })
export const getMe = () => request('/auth/me')
export const updateMe = changes => request('/auth/me', { method: 'PATCH', body: JSON.stringify(changes) })
export const getMyBookings = () => request('/me/bookings')
export const cancelMyBooking = bookingRef => request(`/me/bookings/${encodeURIComponent(bookingRef)}/cancel`, { method: 'POST' })

// ---------------------------------------------------------------- Admin console
const qs = params => {
  const pairs = Object.entries(params || {}).filter(([, value]) => value !== undefined && value !== null && value !== '')
  return pairs.length ? `?${new URLSearchParams(pairs)}` : ''
}
export const adminMe = () => adminRequest('/me')
export const adminDashboard = days => adminRequest(`/dashboard${qs({ days })}`)
export const adminBookings = params => adminRequest(`/bookings${qs(params)}`)
export const adminBooking = ref => adminRequest(`/bookings/${encodeURIComponent(ref)}`)
export const adminCancelBooking = (ref, reason) => adminRequest(`/bookings/${encodeURIComponent(ref)}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) })
export const adminCustomers = params => adminRequest(`/customers${qs(params)}`)
export const adminSetBlocked = (id, isBlocked, reason) => adminRequest(`/customers/${id}`, { method: 'PATCH', body: JSON.stringify({ is_blocked: isBlocked, reason }) })
export const adminCinemas = () => adminRequest('/cinemas')
export const adminSetCinemaActive = (id, isActive) => adminRequest(`/cinemas/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) })
export const adminShows = (cinemaId, date) => adminRequest(`/shows${qs({ cinema_id: cinemaId, date })}`)
export const adminCancelShow = (id, reason) => adminRequest(`/shows/${id}/cancel`, { method: 'POST', body: JSON.stringify({ reason }) })
export const adminStaff = () => adminRequest('/staff')
export const adminCreateStaff = staff => adminRequest('/staff', { method: 'POST', body: JSON.stringify(staff) })
export const adminUpdateStaff = (id, changes) => adminRequest(`/staff/${id}`, { method: 'PATCH', body: JSON.stringify(changes) })
export const adminAudit = params => adminRequest(`/audit${qs(params)}`)

import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { adminLogin, adminLogout, adminMe, adminSession, updateAdminSession } from '../api'
import { useDocumentTitle } from '../utils/hooks'
import Audit from './admin/Audit'
import Bookings from './admin/Bookings'
import CinemasAdmin from './admin/CinemasAdmin'
import Customers from './admin/Customers'
import Dashboard from './admin/Dashboard'
import Films from './admin/Films'
import Staff from './admin/Staff'

// Each section and the permission it needs (the server enforces the same rules).
const SECTIONS = [
  { path: '', label: 'Dashboard', icon: '◧', permission: 'dashboard.view', element: Dashboard },
  { path: 'bookings', label: 'Bookings', icon: '🎟', permission: 'bookings.view', element: Bookings },
  { path: 'films', label: 'Films', icon: '🎬', permission: 'films.manage', element: Films },
  { path: 'cinemas', label: 'Cinemas & shows', icon: '🏛', permission: 'dashboard.view', element: CinemasAdmin },
  { path: 'customers', label: 'Customers', icon: '👥', permission: 'customers.view', element: Customers },
  { path: 'staff', label: 'Staff & roles', icon: '🛡', permission: 'staff.manage', element: Staff },
  { path: 'audit', label: 'Audit log', icon: '🧾', permission: 'audit.view', element: Audit },
]

export default function Admin() {
  const [session, setSession] = useState(adminSession)
  const signedOut = useCallback(() => setSession(null), [])
  useDocumentTitle('CineBook Admin')

  // Refresh role and permissions from the server: they may have changed since sign-in.
  useEffect(() => {
    if (!adminSession()) return undefined
    let active = true
    adminMe()
      .then(me => { if (active) setSession(updateAdminSession({ ...me })) })
      .catch(error => { if (active && error.status === 401) setSession(null) })
    return () => { active = false }
  }, [])

  return session ? <Console session={session} onSignOut={signedOut} /> : <StaffSignIn onSignedIn={setSession} />
}

function StaffSignIn({ onSignedIn }) {
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (!form.username.trim() || !form.password) return setError('Enter your username and password.')
    setBusy(true)
    setError('')
    try {
      onSignedIn(await adminLogin(form.username.trim(), form.password))
    } catch (requestError) {
      setError(requestError.message)
      setForm(current => ({ ...current, password: '' }))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="admin-signin-page">
      <div className="auth-card panel">
        <Link className="brand" to="/"><span className="brand-mark">✦</span>CineBook</Link>
        <span className="eyebrow">STAFF ONLY</span>
        <h1>Admin sign-in<span className="accent">.</span></h1>
        <p className="muted">For CineBook staff. Customers sign in on the main site.</p>
        <form className="auth-form" onSubmit={submit} noValidate>
          <label>Username<input value={form.username} onChange={event => setForm({ ...form, username: event.target.value })} autoComplete="username" /></label>
          <label>Password<input type="password" value={form.password} onChange={event => setForm({ ...form, password: event.target.value })} autoComplete="current-password" /></label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </div>
    </main>
  )
}

function Console({ session, onSignOut }) {
  const permissions = new Set(session.permissions || [])
  // Sessions saved before roles existed have no permission list yet; /admin/me fills it in a moment.
  const can = permission => permissions.size === 0 || permissions.has(permission)
  const sections = SECTIONS.filter(section => can(section.permission))
  const [menuOpen, setMenuOpen] = useState(false)

  async function signOut() {
    await adminLogout().catch(() => {})
    onSignOut()
  }

  return (
    <div className="admin-shell">
      <aside className={`admin-sidebar ${menuOpen ? 'open' : ''}`}>
        <Link className="brand" to="/"><span className="brand-mark">✦</span>CineBook</Link>
        <span className="admin-badge">Admin</span>
        <nav aria-label="Admin sections">
          {sections.map(section => (
            <NavLink key={section.path} to={`/admin${section.path ? `/${section.path}` : ''}`} end={!section.path} onClick={() => setMenuOpen(false)}>
              <span aria-hidden="true">{section.icon}</span>{section.label}
            </NavLink>
          ))}
        </nav>
        <div className="admin-user">
          <span className="avatar" aria-hidden="true">{(session.full_name || session.username)[0].toUpperCase()}</span>
          <div><strong>{session.full_name || session.username}</strong><small>{session.role_label || 'Super admin'}</small></div>
        </div>
        <button type="button" className="button print-button full" onClick={signOut}>Sign out</button>
        <Link className="admin-back" to="/">← Back to the website</Link>
      </aside>
      <div className="admin-main">
        <header className="admin-topbar">
          <button type="button" className="admin-menu-button" aria-label="Open menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(value => !value)}>☰</button>
          <span className="muted">Demo environment · payments and refunds are simulated</span>
        </header>
        <main className="admin-content">
          <Routes>
            {sections.map(section => {
              const Section = section.element
              return <Route key={section.path} path={section.path || undefined} index={!section.path}
                            element={<Section session={session} can={can} onSignOut={onSignOut} />} />
            })}
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../auth'
import Shell from '../components/Shell'
import { useDocumentTitle } from '../utils/hooks'

// Only same-site paths are allowed as the place to return to after signing in.
function safeNext(value) {
  return value && value.startsWith('/') && !value.startsWith('//') ? value : '/'
}

export default function SignIn({ mode = 'signin' }) {
  const { user, signIn, register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const registering = mode === 'register'
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useDocumentTitle(registering ? 'Create account' : 'Sign in')

  if (user) return <Navigate to={next} replace />

  function set(field, value) {
    setForm(current => ({ ...current, [field]: value }))
    setError('')
  }

  async function submit(event) {
    event.preventDefault()
    if (registering && form.full_name.trim().length < 2) return setError('Enter your full name.')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) return setError('Enter a valid email address.')
    if (registering && form.password.length < 8) return setError('Use a password of at least 8 characters.')
    if (!form.password) return setError('Enter your password.')
    setBusy(true)
    try {
      if (registering) {
        await register({ full_name: form.full_name.trim(), email: form.email.trim(), password: form.password, phone: form.phone.trim() || null })
      } else {
        await signIn(form.email.trim(), form.password)
      }
      navigate(next, { replace: true })
    } catch (requestError) {
      setError(requestError.message)
      setForm(current => ({ ...current, password: '' }))
    } finally {
      setBusy(false)
    }
  }

  const other = `${registering ? '/login' : '/register'}${next !== '/' ? `?next=${encodeURIComponent(next)}` : ''}`

  return (
    <Shell>
      <div className="auth-card panel">
        <span className="eyebrow">{registering ? 'NEW TO CINEBOOK' : 'WELCOME BACK'}</span>
        <h1>{registering ? 'Create your account' : 'Sign in'}<span className="accent">.</span></h1>
        <p className="muted">{next.startsWith('/shows/') || next.startsWith('/checkout/')
          ? 'Sign in to hold your seats and book. Your selection is kept.'
          : registering ? 'Book tickets faster and find all your bookings in one place.' : 'Sign in to book tickets and see your bookings.'}</p>
        <form className="auth-form" onSubmit={submit} noValidate>
          {registering && (
            <label>Full name
              <input value={form.full_name} onChange={event => set('full_name', event.target.value)} autoComplete="name" placeholder="e.g. Aditi Sharma" />
            </label>
          )}
          <label>Email
            <input type="email" value={form.email} onChange={event => set('email', event.target.value)} autoComplete="email" placeholder="you@example.com" />
          </label>
          {registering && (
            <label>Mobile number <em>Optional</em>
              <input type="tel" inputMode="tel" value={form.phone} onChange={event => set('phone', event.target.value)} autoComplete="tel" placeholder="e.g. 9812345678" />
            </label>
          )}
          <label>Password {registering && <em>At least 8 characters</em>}
            <input type="password" value={form.password} onChange={event => set('password', event.target.value)}
                   autoComplete={registering ? 'new-password' : 'current-password'} />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button primary full" disabled={busy}>{busy ? 'Please wait…' : registering ? 'Create account' : 'Sign in'}</button>
        </form>
        <p className="auth-switch">
          {registering ? 'Already have an account?' : 'New to CineBook?'} <Link to={other}>{registering ? 'Sign in' : 'Create an account'}</Link>
        </p>
      </div>
    </Shell>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getDemoInbox } from '../api'
import Shell from '../components/Shell'
import SmsText from '../components/SmsText'
import { useDocumentTitle } from '../utils/hooks'

// Phase 2: a pretend phone that shows the demo SMS sent to one registered number.
// The number and access code are kept only for this browser tab (sessionStorage).
const SESSION_KEY = 'cinebook_demo_phone'
const REFRESH_MS = 10000

function savedLogin() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY)) || null
  } catch {
    return null
  }
}

function messageTime(value) {
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata',
  }).format(new Date(value))
}

export default function DemoPhone() {
  useDocumentTitle('Demo Phone')
  const [login, setLogin] = useState(savedLogin)
  const [form, setForm] = useState({ phone: '', accessCode: '' })
  const [inbox, setInbox] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async (details, quiet = false) => {
    if (!quiet) setBusy(true)
    try {
      const data = await getDemoInbox(details.phone, details.accessCode)
      setInbox(data)
      setError('')
      return true
    } catch (requestError) {
      if (requestError.status === 401 || requestError.status === 429) {
        sessionStorage.removeItem(SESSION_KEY)
        setLogin(null)
        setInbox(null)
      }
      setError(requestError.message)
      return false
    } finally {
      if (!quiet) setBusy(false)
    }
  }, [])

  // Open the saved inbox, then check for new messages every 10 seconds.
  useEffect(() => {
    if (!login) return undefined
    const first = setTimeout(() => load(login, true), 0)
    const timer = setInterval(() => load(login, true), REFRESH_MS)
    return () => { clearTimeout(first); clearInterval(timer) }
  }, [login, load])

  async function unlock(event) {
    event.preventDefault()
    const details = { phone: form.phone.trim(), accessCode: form.accessCode.trim() }
    if (!details.phone || !details.accessCode) {
      setError('Enter the demo phone number and the access code.')
      return
    }
    if (await load(details)) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(details))
      setLogin(details)
      setForm({ phone: '', accessCode: '' })
    }
  }

  function lock() {
    sessionStorage.removeItem(SESSION_KEY)
    setLogin(null)
    setInbox(null)
    setError('')
  }

  return (
    <Shell>
      <div className="demo-phone-page">
        <div className="demo-phone-intro">
          <span className="eyebrow">TRAINING DEMO</span>
          <h1>Demo Phone<span className="accent">.</span></h1>
          <p>When a booking is confirmed with the SMS option ticked, CineBook “sends” an SMS to a registered demo number. Real SMS delivery is not used in this demo: the messages appear here instead.</p>
          <p className="muted">Tap the link in a message to open the booking’s chat page.</p>
        </div>

        <div className="phone-frame" aria-label="Demo phone">
          <div className="phone-notch" aria-hidden="true" />
          <div className="phone-screen">
            {!inbox ? (
              <form className="phone-login" onSubmit={unlock} noValidate>
                <span className="phone-lock" aria-hidden="true">✦</span>
                <h2>Unlock the Demo Phone</h2>
                <label>Demo phone number
                  <input type="tel" inputMode="tel" autoComplete="tel" placeholder="e.g. 9812345678"
                         value={form.phone} onChange={event => setForm({ ...form, phone: event.target.value })} />
                </label>
                <label>Access code
                  <input type="password" autoComplete="off" placeholder="Given by your trainer"
                         value={form.accessCode} onChange={event => setForm({ ...form, accessCode: event.target.value })} />
                </label>
                {error && <p className="phone-error" role="alert">{error}</p>}
                <button className="button primary full" disabled={busy}>{busy ? 'Opening…' : 'Open messages'}</button>
              </form>
            ) : (
              <div className="phone-inbox">
                <div className="phone-bar">
                  <div><small>Messages for</small><strong>{inbox.phone}</strong></div>
                  <button type="button" className="phone-bar-button" onClick={lock}>Lock</button>
                </div>
                <div className="sms-thread" aria-live="polite">
                  <div className="sms-sender">CineBook</div>
                  {inbox.messages.length === 0 ? (
                    <p className="sms-empty">No messages yet. Book a ticket with the SMS option ticked, using this number - the message appears here within a few seconds.</p>
                  ) : inbox.messages.map(message => (
                    <article className="sms-bubble" key={message.id}>
                      <p><SmsText text={message.body} /></p>
                      <time>{messageTime(message.created_at)}</time>
                    </article>
                  ))}
                </div>
                {error && <p className="phone-error" role="alert">{error}</p>}
                <p className="phone-refresh">Checks for new messages every 10 seconds</p>
              </div>
            )}
          </div>
        </div>
      </div>
      <p className="demo-phone-back"><Link className="back-link" to="/">← <span>Back to movies</span></Link></p>
    </Shell>
  )
}

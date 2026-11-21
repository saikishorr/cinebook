import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { cancelHold, createBooking, getHold, getShow } from '../api'
import Countdown from '../components/Countdown'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import Shell from '../components/Shell'
import Toast from '../components/Toast'
import { useAuth } from '../auth'
import { clearActiveHold, saveActiveHold } from '../utils/activeHold'
import { money, formatDate, formatTime } from '../utils/format'
import { useDocumentTitle, useSecondsUntil } from '../utils/hooks'

const SERVICE_DOWN = 'Booking service is temporarily unavailable. Please try again.'
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function validate(form) {
  const errors = {}
  if (form.name.trim().length < 2) errors.name = 'Enter your full name (at least 2 characters).'
  if (!form.email.trim()) errors.email = 'Please enter your email.'
  else if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = 'Enter a valid email address.'
  // Phase 2: the SMS needs a mobile number (the server checks it is registered for demo SMS).
  if (form.smsConsent) {
    const digits = form.phone.replace(/\D/g, '')
    if (!digits) errors.phone = 'Enter your mobile number to receive the SMS.'
    else if (digits.length < 10) errors.phone = 'Enter a 10-digit mobile number, e.g. 9812345678.'
  }
  return errors
}

export default function Checkout() {
  const { holdId } = useParams()
  const navigate = useNavigate()
  const [hold, setHold] = useState(null)
  const [show, setShow] = useState(null)
  const [deadline, setDeadline] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [serverExpired, setServerExpired] = useState(false)
  const { user, expired: sessionExpired } = useAuth()
  // Tickets belong to the signed-in account: its name, email and phone fill the form.
  const [form, setForm] = useState(() => ({
    name: user?.full_name || '', email: user?.email || '', phone: user?.phone?.replace(/^\+91/, '') || '', smsConsent: false,
  }))
  const [submitted, setSubmitted] = useState(false)     // show field errors only after the first Pay click
  const [serverFieldErrors, setServerFieldErrors] = useState({})
  const [toast, setToast] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [bookingError, setBookingError] = useState(null)
  useDocumentTitle('Checkout')

  useEffect(() => {
    let active = true
    getHold(holdId)
      .then(async holdData => {
        // Count down from the server's own figure, so a wrong clock on this computer cannot shorten the hold.
        const remaining = Math.max(0, Number(holdData.seconds_remaining) || 0)
        const showData = await getShow(holdData.show_id)
        if (!active) return
        setHold(holdData)
        setShow(showData)
        setDeadline(new Date(Date.now() + remaining * 1000))
        if (holdData.status === 'EXPIRED' || remaining <= 0) setServerExpired(true)
        else saveActiveHold(holdData)
      })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 404) {
          clearActiveHold()
          setError('NOT_FOUND')
        } else {
          setError(requestError.message)
        }
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [holdId])

  const seconds = useSecondsUntil(deadline) ?? 0
  const expired = Boolean(hold) && (serverExpired || (deadline !== null && seconds <= 0))

  useEffect(() => {
    if (expired) clearActiveHold()
  }, [expired])

  const formErrors = { ...(submitted ? validate(form) : {}), ...serverFieldErrors }

  function update(field, value) {
    setForm(current => ({ ...current, [field]: value }))
    if (field === 'phone' || field === 'smsConsent') setServerFieldErrors({})
  }

  async function releaseSeats() {
    try {
      await cancelHold(holdId)
      clearActiveHold()
      setToast('Your seats have been released.')
      setTimeout(() => navigate(`/shows/${hold.show_id}`), 700)
    } catch (requestError) {
      if (requestError.status === 404) {
        clearActiveHold()
        setError('NOT_FOUND')
      } else {
        setError(requestError.message)
      }
    }
  }

  async function pay(event) {
    event.preventDefault()
    if (submitting || expired) return
    setSubmitted(true)
    if (Object.keys(validate(form)).length) return
    setSubmitting(true)
    setBookingError(null)
    try {
      const result = await createBooking(holdId, {
        fullName: form.name.trim(), email: form.email.trim(), phone: form.phone.trim() || null, smsConsent: form.smsConsent,
      })
      clearActiveHold()
      navigate(`/booking/${result.booking_ref}`)
    } catch (requestError) {
      if (requestError.status === 409 && requestError.message === 'Your hold has expired') {
        setServerExpired(true)
      } else if (requestError.status === 422 && /number|SMS/.test(requestError.message)) {
        // Phase 2: show phone problems (e.g. "not registered for demo SMS") next to the phone field.
        setServerFieldErrors({ phone: requestError.message })
      } else if (requestError.status === 401) {
        sessionExpired()
        navigate(`/login?next=${encodeURIComponent(`/checkout/${holdId}`)}`)
      } else if (requestError.status === 503) {
        setBookingError(SERVICE_DOWN)
      } else {
        setBookingError(requestError.message)
      }
      setSubmitting(false)
    }
  }

  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(`/checkout/${holdId}`)}`} replace />

  const seats = hold?.seats || []
  const total = Number(hold?.total_amount || 0)

  return (
    <Shell>
      {loading ? <LoadingState /> : error === 'NOT_FOUND' ? (
        <div className="state-panel">
          <span className="state-icon">⌁</span>
          <h1>Booking session not found</h1>
          <p>This booking session may have expired or no longer exists.</p>
          <Link className="button primary" to="/">Back to movies</Link>
        </div>
      ) : error ? <ErrorState message={error} /> : expired ? (
        <div className="state-panel expired">
          <span className="state-icon">◷</span>
          <span className="eyebrow">TIME'S UP</span>
          <h1>Your hold has expired</h1>
          <p>Those seats have been released and are available for other customers.</p>
          <Link className="button primary" to={`/shows/${hold.show_id}`}>Choose seats again</Link>
        </div>
      ) : (
        <>
          <Link className="back-link" to={`/shows/${hold.show_id}`}>← <span>Back to seats</span></Link>
          <div className="section-heading checkout-title">
            <div><span className="eyebrow">ALMOST THERE</span><h1>Complete your booking<span className="accent">.</span></h1></div>
            <Countdown seconds={seconds} />
          </div>
          <div className="checkout-layout">
            <section className="checkout-details panel">
              <span className="eyebrow">BOOKING DETAILS</span>
              <h2>{show.movie_title}</h2>
              <div className="booking-facts">
                {show.cinema_name && <span>{show.cinema_name}, {show.cinema_area}</span>}
                <span>{show.screen_name}</span>
                <span>{formatDate(show.start_time)}</span>
                <span>{formatTime(show.start_time)}</span>
              </div>
              <div className="seat-pills">
                {seats.map(seat => <span key={seat.id}>{seat.row_label}{seat.seat_number}</span>)}
              </div>
              <div className="form-heading"><span className="eyebrow">THE TICKETS ARE FOR</span><h3>Your details</h3></div>
              <form className="customer-form" onSubmit={pay} noValidate>
                <label>Full name
                  <input value={form.name} onChange={event => update('name', event.target.value)} placeholder="e.g. Aditi Sharma"
                         autoComplete="name" aria-invalid={Boolean(formErrors.name)} />
                  {formErrors.name && <small>{formErrors.name}</small>}
                </label>
                <label>Email address
                  <input type="email" value={form.email} onChange={event => update('email', event.target.value)} placeholder="you@example.com"
                         autoComplete="email" aria-invalid={Boolean(formErrors.email)} readOnly={Boolean(user)}
                         title={user ? 'Tickets are sent to your account email' : undefined} />
                  {formErrors.email && <small>{formErrors.email}</small>}
                </label>
                <label>Mobile number <em>{form.smsConsent ? 'Needed for the SMS' : 'Optional'}</em>
                  <input type="tel" value={form.phone} onChange={event => update('phone', event.target.value)} placeholder="e.g. 9812345678"
                         autoComplete="tel" inputMode="tel" aria-invalid={Boolean(formErrors.phone)} />
                  {formErrors.phone && <small>{formErrors.phone}</small>}
                </label>
                <label className="sms-consent">
                  <input type="checkbox" checked={form.smsConsent} onChange={event => update('smsConsent', event.target.checked)} />
                  <span>Send me an SMS with my booking and a chat link <em>Demo: registered numbers only</em></span>
                </label>
                <button className="button primary full pay-button" disabled={submitting}>
                  {submitting ? 'Processing…' : `Pay ${money(total)}`}
                </button>
                <p className="payment-note">Payment is simulated for this demo.</p>
                {bookingError && <div className="booking-error" role="alert"><span>{bookingError}</span>{bookingError !== SERVICE_DOWN && <Link to={`/shows/${hold.show_id}`}>Back to seat map</Link>}</div>}
              </form>
            </section>
            <aside className="order-summary panel">
              <span className="eyebrow">ORDER SUMMARY</span>
              <h2>Your tickets</h2>
              <div className="order-line"><span>Seats <small>({seats.length})</small></span><strong>{money(total)}</strong></div>
              <div className="order-seat-list">
                {seats.map(seat => <span key={seat.id}>{seat.row_label}{seat.seat_number}</span>)}
              </div>
              <div className="summary-total"><span>Total</span><strong>{money(total)}</strong></div>
              <Countdown seconds={seconds} compact />
              <button type="button" className="cancel-button" onClick={releaseSeats}>Cancel and release seats</button>
            </aside>
          </div>
          <Toast message={toast} />
        </>
      )}
    </Shell>
  )
}

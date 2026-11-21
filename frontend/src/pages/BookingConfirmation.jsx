import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { cancelMyBooking, getBooking } from '../api'
import { useAuth } from '../auth'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import Shell from '../components/Shell'
import { downloadBookingCalendar } from '../utils/calendar'
import { formatDate, formatTime, money } from '../utils/format'
import { useDocumentTitle } from '../utils/hooks'

export default function BookingConfirmation() {
  const { bookingRef } = useParams()
  const [booking, setBooking] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState('')
  const [waiting, setWaiting] = useState(false)
  const [retry, setRetry] = useState(0)
  const [copied, setCopied] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState('')
  const { user } = useAuth()

  async function cancelBooking() {
    if (!window.confirm(`Cancel booking ${bookingRef}? You will get a full (simulated) refund.`)) return
    setCancelling(true)
    setCancelError('')
    try {
      setBooking(await cancelMyBooking(bookingRef))
    } catch (requestError) {
      setCancelError(requestError.message)
    } finally {
      setCancelling(false)
    }
  }
  useDocumentTitle(`Booking ${bookingRef}`)

  async function copyReference() {
    try {
      await navigator.clipboard.writeText(bookingRef)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard blocked: the reference is on screen to copy by hand.
    }
  }

  const fetchBooking = useCallback(async () => {
    try {
      const data = await getBooking(bookingRef)
      setBooking(data)
      setError('')
      setNotFound(false)
      return data
    } catch (requestError) {
      if (requestError.status === 404) setNotFound(true)
      else setError(requestError.message)
      return null
    } finally {
      setLoading(false)
    }
  }, [bookingRef])

  useEffect(() => {
    let active = true
    let intervalId
    let timeoutId
    const started = Date.now()

    async function check() {
      const data = await fetchBooking()
      if (!active || !data || data.status !== 'PENDING') return
      if (Date.now() - started >= 60000) {
        setWaiting(true)
        return
      }
      intervalId = setTimeout(check, 2000)
    }

    check()
    timeoutId = setTimeout(() => {
      if (active) setWaiting(true)
    }, 60000)
    return () => {
      active = false
      clearTimeout(intervalId)
      clearTimeout(timeoutId)
    }
  }, [fetchBooking, retry])

  if (loading) return <Shell><LoadingState /></Shell>
  if (notFound) return <Shell><div className="state-panel"><span className="state-icon">!</span><h1>Booking not found</h1><p>We couldn't find booking reference {bookingRef}.</p><Link className="button primary" to="/">Back to movies</Link></div></Shell>
  if (error && !booking) return <Shell><ErrorState message={error} onRetry={() => { setLoading(true); setRetry(value => value + 1) }} /></Shell>
  if (!booking) return null

  return (
    <Shell>
      {booking.status === 'PENDING' ? waiting ? (
        <div className="state-panel"><span className="state-icon">…</span><h1>This is taking longer than usual</h1><p>Your booking reference is {bookingRef}; we'll email you once it's confirmed.</p><button className="button primary" onClick={() => { setWaiting(false); setLoading(true); setRetry(value => value + 1) }}>Check again</button></div>
      ) : (
        <div className="state-panel pending-panel"><span className="pending-spinner" aria-hidden="true" /><span className="eyebrow">BOOKING {bookingRef}</span><h1>Confirming your booking…</h1><p>We're completing your payment and preparing your ticket.</p></div>
      ) : booking.status === 'CONFIRMED' ? (
        <section className="ticket-wrap">
          <div className="ticket-card">
            <div className="ticket-top"><span className="eyebrow">CINEBOOK · ADMIT ONE</span><span className="ticket-status">CONFIRMED</span><span className="ticket-demo">DEMO · NOT VALID FOR ENTRY</span></div>
            <p className="ticket-ref-label">BOOKING REFERENCE</p>
            <div className="ticket-ref-row"><h1 className="ticket-ref">{booking.booking_ref}</h1><button type="button" className="copy-button" onClick={copyReference} aria-label="Copy booking reference">{copied ? 'Copied ✓' : 'Copy'}</button></div>
            <div className="ticket-rule" />
            <span className="eyebrow">YOUR MOVIE</span><h2 className="ticket-movie">{booking.movie_title}</h2>
            <div className="ticket-details">
              <div><small>DATE</small><strong>{formatDate(booking.start_time)}</strong></div>
              <div><small>TIME</small><strong>{formatTime(booking.start_time)}</strong></div>
              {booking.cinema_name && <div className="ticket-wide"><small>CINEMA</small><strong>{booking.cinema_name}</strong>{booking.cinema_address && <span className="ticket-address">{booking.cinema_address}</span>}</div>}
              <div><small>SCREEN</small><strong>{booking.screen_name}{booking.screen_format && booking.screen_format !== '2D' ? ` · ${booking.screen_format}` : ''}</strong></div>
              <div><small>SEATS</small><strong>{(booking.seats || []).map(seat => `${seat.row_label}${seat.seat_number}${seat.seat_type === 'RECLINER' ? ' (Recliner)' : seat.seat_type === 'PREMIUM' ? ' ★' : ''}`).join(' · ')}</strong></div>
            </div>
            <div className="ticket-payment"><span>Total paid<strong>{money(booking.total_amount)}</strong></span><span>Payment reference<strong>{booking.payment_ref || '—'}</strong></span></div>
            <p className="ticket-email">A confirmation email has been sent to {booking.email_masked || booking.email}.</p>
            {booking.sms_consent && <p className="ticket-sms">A demo SMS with a chat link has been sent to {booking.sms_phone_masked}. <Link to="/demo-phone">Open the Demo Phone</Link> to see it.</p>}
          </div>
          <div className="ticket-actions"><Link className="button primary" to="/">Book another movie</Link><button type="button" className="button print-button" onClick={() => downloadBookingCalendar(booking, booking.duration_minutes)}>Add to calendar</button><button type="button" className="button print-button" onClick={() => window.print()}>Print ticket</button>
            {user && booking.cancellable && booking.email?.toLowerCase() === user.email.toLowerCase() && (
              <button type="button" className="button danger-button" disabled={cancelling} onClick={cancelBooking}>{cancelling ? 'Cancelling…' : 'Cancel booking'}</button>
            )}</div>
          {booking.cancellable && booking.cancel_deadline && <p className="ticket-note">Free cancellation until {formatDate(booking.cancel_deadline)}, {formatTime(booking.cancel_deadline)}.</p>}
          {cancelError && <p className="form-error ticket-note" role="alert">{cancelError}</p>}
        </section>
      ) : (
        <div className="state-panel"><span className="state-icon">!</span><h1>{booking.status === 'FAILED' ? 'Booking could not be completed' : 'Booking cancelled'}</h1><p>{booking.status === 'FAILED' ? 'Your payment was not completed. Please choose a movie and try again.' : `This booking was cancelled${booking.refund_ref ? ` and refunded (reference ${booking.refund_ref})` : ''}.`}</p><Link className="button primary" to="/">Back to movies</Link></div>
      )}
    </Shell>
  )
}

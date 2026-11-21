import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { cancelMyBooking, getMyBookings } from '../api'
import { useAuth } from '../auth'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import Poster from '../components/Poster'
import Shell from '../components/Shell'
import Toast from '../components/Toast'
import { formatDate, formatTime, money } from '../utils/format'
import { useDocumentTitle } from '../utils/hooks'

const STATUS_LABEL = { CONFIRMED: 'Confirmed', PENDING: 'Confirming…', CANCELLED: 'Cancelled', FAILED: 'Failed' }

export default function MyBookings() {
  const { user, expired } = useAuth()
  const [bookings, setBookings] = useState(null)
  const [error, setError] = useState('')
  const [busyRef, setBusyRef] = useState(null)
  const [toast, setToast] = useState('')
  const [now] = useState(() => Date.now())     // splits upcoming from past; fixed for this visit
  useDocumentTitle('My bookings')

  const load = useCallback(() => {
    let active = true
    getMyBookings()
      .then(data => { if (active) setBookings(data) })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 401) expired()
        else setError(requestError.message)
      })
    return () => { active = false }
  }, [expired])

  useEffect(() => (user ? load() : undefined), [user, load])

  useEffect(() => {
    if (!toast) return undefined
    const id = setTimeout(() => setToast(''), 4000)
    return () => clearTimeout(id)
  }, [toast])

  const [upcoming, past] = useMemo(() => {
    const list = bookings || []
    return [list.filter(b => new Date(b.start_time).getTime() > now && b.status !== 'CANCELLED'),
      list.filter(b => new Date(b.start_time).getTime() <= now || b.status === 'CANCELLED')]
  }, [bookings, now])

  if (!user) return <Navigate to="/login?next=/my-bookings" replace />

  async function cancel(booking) {
    if (!window.confirm(`Cancel booking ${booking.booking_ref} for ${booking.movie_title}? You will get a full (simulated) refund.`)) return
    setBusyRef(booking.booking_ref)
    try {
      await cancelMyBooking(booking.booking_ref)
      setToast(`Booking ${booking.booking_ref} cancelled. Refund issued.`)
      load()
    } catch (requestError) {
      setToast(requestError.message)
    } finally {
      setBusyRef(null)
    }
  }

  const card = booking => (
    <article className={`my-booking ${booking.status.toLowerCase()}`} key={booking.booking_ref}>
      <Poster movie={{ title: booking.movie_title, poster_url: booking.poster_url }} />
      <div className="my-booking-body">
        <div className="my-booking-top">
          <span className={`status-pill ${booking.status.toLowerCase()}`}>{STATUS_LABEL[booking.status] || booking.status}</span>
          <Link to={`/booking/${booking.booking_ref}`} className="my-booking-ref">{booking.booking_ref}</Link>
        </div>
        <h3>{booking.movie_title}</h3>
        <p>{formatDate(booking.start_time)} · {formatTime(booking.start_time)} · {booking.cinema_name}, {booking.cinema_area}</p>
        <p className="muted">{booking.screen_name} · Seats {booking.seats.join(', ') || '—'} · {money(booking.total_amount)}</p>
        <div className="my-booking-actions">
          <Link className="button print-button" to={`/booking/${booking.booking_ref}`}>View ticket</Link>
          {booking.cancellable && (
            <button type="button" className="button danger-button" disabled={busyRef === booking.booking_ref} onClick={() => cancel(booking)}>
              {busyRef === booking.booking_ref ? 'Cancelling…' : 'Cancel booking'}
            </button>
          )}
        </div>
      </div>
    </article>
  )

  return (
    <Shell>
      <div className="section-heading">
        <div><span className="eyebrow">HELLO, {user.full_name.split(' ')[0].toUpperCase()}</span><h1 className="page-title">My bookings<span className="accent">.</span></h1></div>
      </div>
      {error ? <ErrorState message={error} /> : !bookings ? <LoadingState /> : bookings.length === 0 ? (
        <EmptyState title="No bookings yet">Pick a movie and your seats, and your tickets will appear here. <Link to="/">Browse movies</Link></EmptyState>
      ) : (
        <>
          <h2 className="list-heading">Upcoming</h2>
          {upcoming.length ? <div className="my-bookings">{upcoming.map(card)}</div> : <p className="muted">No upcoming shows.</p>}
          {past.length > 0 && <><h2 className="list-heading">Past and cancelled</h2><div className="my-bookings">{past.map(card)}</div></>}
        </>
      )}
      <Toast message={toast} />
    </Shell>
  )
}

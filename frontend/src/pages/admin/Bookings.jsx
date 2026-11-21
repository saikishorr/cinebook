import { useCallback, useEffect, useState } from 'react'
import { adminBooking, adminBookings, adminCancelBooking, adminCinemas } from '../../api'
import ErrorState from '../../components/ErrorState'
import Toast from '../../components/Toast'
import { formatDate, formatTime, money } from '../../utils/format'
import { Pager, ReasonDialog, StatusPill, shortDateTime, useToast } from './ui'

const LIMIT = 25

// Find any booking, see every detail, and cancel + refund with a reason.
export default function Bookings({ can, onSignOut }) {
  const [filters, setFilters] = useState({ q: '', status: '', cinema_id: '', date: '' })
  const [applied, setApplied] = useState(filters)
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState(null)
  const [cinemas, setCinemas] = useState([])
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useToast()

  const fail = useCallback(requestError => {
    if (requestError.status === 401) onSignOut()
    else setError(requestError.message)
  }, [onSignOut])

  useEffect(() => {
    adminCinemas().then(setCinemas).catch(() => {})
  }, [])

  useEffect(() => {
    let active = true
    adminBookings({ ...applied, limit: LIMIT, offset })
      .then(data => { if (active) { setPage(data); setError('') } })
      .catch(requestError => { if (active) fail(requestError) })
    return () => { active = false }
  }, [applied, offset, fail])

  function search(event) {
    event.preventDefault()
    setOffset(0)
    setApplied({ ...filters })
  }

  async function open(ref) {
    try {
      setSelected(await adminBooking(ref))
    } catch (requestError) {
      fail(requestError)
    }
  }

  async function cancel(reason) {
    setBusy(true)
    try {
      const updated = await adminCancelBooking(selected.booking_ref, reason)
      setSelected(updated)
      setCancelOpen(false)
      setToast(`Booking ${updated.booking_ref} cancelled. Refund ${updated.refund_ref}.`)
      setApplied(current => ({ ...current }))          // refresh the list
    } catch (requestError) {
      setToast(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">SALES</span><h1 className="admin-title">Bookings</h1></div>
      </div>
      <form className="admin-filters" onSubmit={search}>
        <input type="search" value={filters.q} onChange={event => setFilters({ ...filters, q: event.target.value })}
               placeholder="Booking ref, email or name" aria-label="Search bookings" />
        <select value={filters.status} onChange={event => setFilters({ ...filters, status: event.target.value })} aria-label="Status">
          <option value="">All statuses</option>
          {['CONFIRMED', 'PENDING', 'CANCELLED', 'FAILED'].map(status => <option key={status} value={status}>{status[0] + status.slice(1).toLowerCase()}</option>)}
        </select>
        <select value={filters.cinema_id} onChange={event => setFilters({ ...filters, cinema_id: event.target.value })} aria-label="Cinema">
          <option value="">All cinemas</option>
          {cinemas.map(cinema => <option key={cinema.id} value={cinema.id}>{cinema.name}</option>)}
        </select>
        <input type="date" value={filters.date} onChange={event => setFilters({ ...filters, date: event.target.value })} aria-label="Show date" />
        <button className="button primary">Search</button>
      </form>

      {error ? <ErrorState message={error} /> : !page ? <p className="muted">Loading bookings…</p> : (
        <>
          <div className="table-wrap">
            <table className="admin-table">
              <thead><tr><th>Booking</th><th>Customer</th><th>Movie & cinema</th><th>Show</th><th>Seats</th><th>Amount</th><th>Status</th></tr></thead>
              <tbody>
                {page.items.map(row => (
                  <tr key={row.booking_ref} onClick={() => open(row.booking_ref)} className="clickable" tabIndex={0}
                      onKeyDown={event => { if (event.key === 'Enter') open(row.booking_ref) }}>
                    <td><strong>{row.booking_ref}</strong><small>{shortDateTime(row.created_at)}</small></td>
                    <td>{row.customer_name}<small>{row.email}{row.user_id ? '' : ' · guest'}</small></td>
                    <td>{row.movie_title}<small>{row.cinema_name} · {row.screen_name}</small></td>
                    <td>{shortDateTime(row.start_time)}</td>
                    <td>{row.seats_count}</td>
                    <td>{money(row.total_amount)}</td>
                    <td><StatusPill status={row.status} /></td>
                  </tr>
                ))}
                {page.items.length === 0 && <tr><td colSpan={7} className="muted">No bookings match.</td></tr>}
              </tbody>
            </table>
          </div>
          <Pager total={page.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}

      {selected && (
        <aside className="admin-drawer" aria-label={`Booking ${selected.booking_ref}`}>
          <div className="drawer-head">
            <div><span className="eyebrow">BOOKING</span><h2>{selected.booking_ref}</h2></div>
            <button type="button" className="drawer-close" aria-label="Close" onClick={() => setSelected(null)}>×</button>
          </div>
          <StatusPill status={selected.status} />
          <dl className="detail-list">
            <dt>Customer</dt><dd>{selected.full_name}<small>{selected.email}{selected.phone ? ` · ${selected.phone}` : ''}</small></dd>
            <dt>Account</dt><dd>{selected.user_id ? `Customer #${selected.user_id}` : 'Guest booking (before accounts)'}</dd>
            <dt>Movie</dt><dd>{selected.movie_title} <small>{selected.movie_language}</small></dd>
            <dt>Cinema</dt><dd>{selected.cinema_name}<small>{selected.cinema_area} · {selected.screen_name}</small></dd>
            <dt>Show</dt><dd>{formatDate(selected.start_time)}, {formatTime(selected.start_time)}</dd>
            <dt>Seats</dt><dd>{selected.seats.map(seat => `${seat.row_label}${seat.seat_number}${seat.seat_type !== 'REGULAR' ? ` (${seat.seat_type.toLowerCase()})` : ''}`).join(', ') || '— (released)'}</dd>
            <dt>Total</dt><dd>{money(selected.total_amount)}</dd>
            <dt>Payment</dt><dd>{selected.payment_ref || '—'}</dd>
            {selected.refund_ref && <><dt>Refund</dt><dd>{selected.refund_ref}<small>{selected.cancelled_by} · {shortDateTime(selected.cancelled_at)}</small></dd></>}
            <dt>Booked</dt><dd>{shortDateTime(selected.created_at)}</dd>
          </dl>
          {can('bookings.cancel') && ['CONFIRMED', 'PENDING'].includes(selected.status) && (
            <button type="button" className="button danger-button full" onClick={() => setCancelOpen(true)}>Cancel & refund</button>
          )}
        </aside>
      )}
      <ReasonDialog open={cancelOpen} busy={busy} title={`Cancel ${selected?.booking_ref}?`} confirmLabel="Cancel & refund"
                    message="The seats are released, the customer gets a full (simulated) refund and a cancellation email. Staff cancellations ignore the 2-hour customer cutoff."
                    onConfirm={cancel} onClose={() => setCancelOpen(false)} />
      <Toast message={toast} />
    </div>
  )
}

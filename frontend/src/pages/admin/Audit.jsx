import { useEffect, useState } from 'react'
import { adminAudit } from '../../api'
import ErrorState from '../../components/ErrorState'
import { Pager, shortDateTime } from './ui'

const LIMIT = 50
const ACTIONS = [
  ['', 'All actions'], ['booking.', 'Bookings'], ['show.', 'Shows'], ['film.', 'Films'],
  ['cinema.', 'Cinemas'], ['customer.', 'Customers'], ['staff.', 'Staff'],
]
const ACTION_TEXT = {
  'booking.cancel': 'cancelled booking', 'show.cancel': 'cancelled show', 'film.activate': 'switched on film',
  'film.deactivate': 'switched off film', 'film.add': 'added film', 'cinema.activate': 'switched on cinema',
  'cinema.deactivate': 'switched off cinema', 'customer.block': 'blocked customer', 'customer.unblock': 'unblocked customer',
  'staff.create': 'created staff account', 'staff.update': 'changed staff account',
}

// Who did what, and when. Read-only.
export default function Audit({ onSignOut }) {
  const [action, setAction] = useState('')
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    adminAudit({ action, limit: LIMIT, offset })
      .then(data => { if (active) setPage(data) })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 401) onSignOut()
        else setError(requestError.message)
      })
    return () => { active = false }
  }, [action, offset, onSignOut])

  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">SECURITY</span><h1 className="admin-title">Audit log</h1></div>
        <select value={action} onChange={event => { setAction(event.target.value); setOffset(0) }} aria-label="Filter actions">
          {ACTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>
      {error ? <ErrorState message={error} /> : !page ? <p className="muted">Loading…</p> : (
        <>
          <ul className="audit-list">
            {page.items.map(item => (
              <li key={item.id}>
                <time>{shortDateTime(item.created_at)}</time>
                <div>
                  <strong>{item.admin_username}</strong> {ACTION_TEXT[item.action] || item.action}
                  {item.target_id && <> <code>{item.target_type} {item.target_id}</code></>}
                  {Object.keys(item.details).length > 0 && (
                    <small>{Object.entries(item.details).filter(([, value]) => value !== null && value !== undefined)
                      .map(([key, value]) => `${key.replace(/_/g, ' ')}: ${Array.isArray(value) ? value.join(', ') || 'none' : value}`).join(' · ')}</small>
                  )}
                </div>
              </li>
            ))}
            {page.items.length === 0 && <li className="muted">No actions recorded yet.</li>}
          </ul>
          <Pager total={page.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </div>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { adminCustomers, adminSetBlocked } from '../../api'
import ErrorState from '../../components/ErrorState'
import Toast from '../../components/Toast'
import { money } from '../../utils/format'
import { Pager, ReasonDialog, shortDateTime, useToast } from './ui'

const LIMIT = 25

// Customer accounts: search, see their spend, and block abuse (blocking signs them out everywhere).
export default function Customers({ can, onSignOut }) {
  const [query, setQuery] = useState('')
  const [applied, setApplied] = useState('')
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState(null)
  const [error, setError] = useState('')
  const [blocking, setBlocking] = useState(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useToast()
  const [reload, setReload] = useState(0)

  const fail = useCallback(requestError => {
    if (requestError.status === 401) onSignOut()
    else setError(requestError.message)
  }, [onSignOut])

  useEffect(() => {
    let active = true
    adminCustomers({ q: applied, limit: LIMIT, offset })
      .then(data => { if (active) setPage(data) })
      .catch(requestError => { if (active) fail(requestError) })
    return () => { active = false }
  }, [applied, offset, fail, reload])

  async function setBlocked(customer, isBlocked, reason) {
    setBusy(true)
    try {
      await adminSetBlocked(customer.id, isBlocked, reason)
      setToast(`${customer.full_name} is ${isBlocked ? 'blocked and signed out' : 'unblocked'}.`)
      setBlocking(null)
      setReload(value => value + 1)
    } catch (requestError) {
      setToast(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">PEOPLE</span><h1 className="admin-title">Customers</h1></div>
        {page && <span className="muted">{page.total} accounts</span>}
      </div>
      <form className="admin-filters" onSubmit={event => { event.preventDefault(); setOffset(0); setApplied(query.trim()) }}>
        <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Name, email or phone" aria-label="Search customers" />
        <button className="button primary">Search</button>
      </form>
      {error ? <ErrorState message={error} /> : !page ? <p className="muted">Loading customers…</p> : (
        <>
          <div className="table-wrap">
            <table className="admin-table">
              <thead><tr><th>Customer</th><th>Phone</th><th>Bookings</th><th>Spent</th><th>Joined</th><th>Last sign-in</th><th>Status</th></tr></thead>
              <tbody>
                {page.items.map(customer => (
                  <tr key={customer.id}>
                    <td><strong>{customer.full_name}</strong><small>{customer.email}</small></td>
                    <td>{customer.phone || '—'}</td>
                    <td>{customer.bookings}</td>
                    <td>{money(customer.spent)}</td>
                    <td>{shortDateTime(customer.created_at)}</td>
                    <td>{shortDateTime(customer.last_login_at)}</td>
                    <td>
                      <span className={`status-pill ${customer.is_blocked ? 'cancelled' : 'confirmed'}`}>{customer.is_blocked ? 'Blocked' : 'Active'}</span>
                      {can('customers.block') && (customer.is_blocked
                        ? <button type="button" className="link-button" disabled={busy} onClick={() => setBlocked(customer, false)}>Unblock</button>
                        : <button type="button" className="link-button danger-link" onClick={() => setBlocking(customer)}>Block</button>)}
                    </td>
                  </tr>
                ))}
                {page.items.length === 0 && <tr><td colSpan={7} className="muted">No customers found.</td></tr>}
              </tbody>
            </table>
          </div>
          <Pager total={page.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
      <ReasonDialog open={Boolean(blocking)} busy={busy} confirmLabel="Block customer" title={`Block ${blocking?.full_name}?`}
                    message="They are signed out at once and cannot sign in or book until unblocked. Existing bookings stay valid."
                    onConfirm={reason => setBlocked(blocking, true, reason)} onClose={() => setBlocking(null)} />
      <Toast message={toast} />
    </div>
  )
}

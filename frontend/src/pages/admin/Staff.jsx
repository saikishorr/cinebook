import { useCallback, useEffect, useState } from 'react'
import { adminCreateStaff, adminStaff, adminUpdateStaff } from '../../api'
import ErrorState from '../../components/ErrorState'
import Toast from '../../components/Toast'
import { shortDateTime, useToast } from './ui'

const ROLES = [
  { value: 'SUPER_ADMIN', label: 'Super admin', can: 'Everything, including staff accounts and the audit log' },
  { value: 'MANAGER', label: 'Manager', can: 'Films, cinemas and shows, blocking customers, plus everything Support can do' },
  { value: 'SUPPORT', label: 'Support', can: 'Dashboard, bookings and customers; can cancel and refund bookings' },
]

// Staff accounts and their roles. Only super admins see this page.
export default function Staff({ session, onSignOut }) {
  const [staff, setStaff] = useState(null)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ username: '', full_name: '', role: 'SUPPORT', password: '' })
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useToast()

  const load = useCallback(() => {
    adminStaff().then(setStaff).catch(requestError => {
      if (requestError.status === 401) onSignOut()
      else setError(requestError.message)
    })
  }, [onSignOut])

  useEffect(() => { load() }, [load])

  async function create(event) {
    event.preventDefault()
    if (!form.username.trim() || form.full_name.trim().length < 2 || form.password.length < 8) {
      return setToast('Enter a username, a full name and a password of at least 8 characters.')
    }
    setBusy(true)
    try {
      const created = await adminCreateStaff({ ...form, username: form.username.trim(), full_name: form.full_name.trim() })
      setToast(`${created.full_name} can now sign in as ${created.role_label}.`)
      setForm({ username: '', full_name: '', role: 'SUPPORT', password: '' })
      load()
    } catch (requestError) {
      setToast(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  async function change(member, changes, message) {
    try {
      await adminUpdateStaff(member.id, changes)
      setToast(message)
      load()
    } catch (requestError) {
      setToast(requestError.message)
    }
  }

  function resetPassword(member) {
    const password = window.prompt(`New password for ${member.username} (at least 8 characters). They will be signed out.`)
    if (password === null) return
    if (password.length < 8) return setToast('Passwords need at least 8 characters.')
    change(member, { password }, `Password reset for ${member.username}.`)
  }

  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">ACCESS</span><h1 className="admin-title">Staff & roles</h1></div>
      </div>
      <div className="role-cards">
        {ROLES.map(role => <div key={role.value} className="panel role-card"><strong>{role.label}</strong><small>{role.can}</small></div>)}
      </div>

      {error ? <ErrorState message={error} /> : !staff ? <p className="muted">Loading staff…</p> : (
        <div className="table-wrap">
          <table className="admin-table">
            <thead><tr><th>Staff member</th><th>Role</th><th>Last sign-in</th><th>Status</th><th /></tr></thead>
            <tbody>
              {staff.map(member => {
                const self = member.username === session.username
                return (
                  <tr key={member.id} className={member.is_active ? '' : 'muted-row'}>
                    <td><strong>{member.full_name || member.username}</strong><small>@{member.username}{self ? ' · you' : ''}</small></td>
                    <td>
                      <select value={member.role} disabled={self} aria-label={`Role of ${member.username}`}
                              onChange={event => change(member, { role: event.target.value }, `${member.username} is now ${ROLES.find(r => r.value === event.target.value).label}.`)}>
                        {ROLES.map(role => <option key={role.value} value={role.value}>{role.label}</option>)}
                      </select>
                    </td>
                    <td>{shortDateTime(member.last_login_at)}</td>
                    <td><span className={`status-pill ${member.is_active ? 'confirmed' : 'cancelled'}`}>{member.is_active ? 'Active' : 'Disabled'}</span></td>
                    <td className="row-actions">
                      <button type="button" className="link-button" onClick={() => resetPassword(member)}>Reset password</button>
                      {!self && (
                        <button type="button" className={`link-button ${member.is_active ? 'danger-link' : ''}`}
                                onClick={() => change(member, { is_active: !member.is_active }, `${member.username} ${member.is_active ? 'disabled and signed out' : 'enabled'}.`)}>
                          {member.is_active ? 'Disable' : 'Enable'}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <section className="panel admin-card">
        <h2>Add a staff member</h2>
        <form className="admin-filters staff-form" onSubmit={create}>
          <input value={form.username} onChange={event => setForm({ ...form, username: event.target.value })} placeholder="Username" aria-label="Username" autoComplete="off" />
          <input value={form.full_name} onChange={event => setForm({ ...form, full_name: event.target.value })} placeholder="Full name" aria-label="Full name" />
          <select value={form.role} onChange={event => setForm({ ...form, role: event.target.value })} aria-label="Role">
            {ROLES.map(role => <option key={role.value} value={role.value}>{role.label}</option>)}
          </select>
          <input type="password" value={form.password} onChange={event => setForm({ ...form, password: event.target.value })}
                 placeholder="Temporary password" aria-label="Temporary password" autoComplete="new-password" />
          <button className="button primary" disabled={busy}>{busy ? 'Adding…' : 'Add staff'}</button>
        </form>
      </section>
      <Toast message={toast} />
    </div>
  )
}

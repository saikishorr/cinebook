import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminCancelShow, adminCinemas, adminSetCinemaActive, adminShows } from '../../api'
import DayTabs from '../../components/DayTabs'
import ErrorState from '../../components/ErrorState'
import Toast from '../../components/Toast'
import { formatTime, money, nextDays } from '../../utils/format'
import { ReasonDialog, StatusPill, useToast } from './ui'

// Cinemas (switch a venue on or off) and each cinema's shows by day (occupancy, revenue, cancel a show).
export default function CinemasAdmin({ can, onSignOut }) {
  const [cinemas, setCinemas] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const days = useMemo(() => nextDays(8), [])
  const [day, setDay] = useState(days[0])
  const [shows, setShows] = useState(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [cancelShow, setCancelShow] = useState(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useToast()
  const [reload, setReload] = useState(0)

  const fail = useCallback(requestError => {
    if (requestError.status === 401) onSignOut()
    else setError(requestError.message)
  }, [onSignOut])

  useEffect(() => {
    let active = true
    adminCinemas()
      .then(data => {
        if (!active) return
        setCinemas(data)
        setSelectedId(current => current ?? data.find(cinema => cinema.is_active)?.id ?? null)
      })
      .catch(requestError => { if (active) fail(requestError) })
    return () => { active = false }
  }, [fail, reload])

  useEffect(() => {
    if (!selectedId) return undefined
    let active = true
    adminShows(selectedId, day)
      .then(data => { if (active) setShows(data) })
      .catch(requestError => { if (active) fail(requestError) })
    return () => { active = false }
  }, [selectedId, day, fail, reload])

  async function toggle(cinema) {
    const verb = cinema.is_active ? 'Switch off' : 'Switch on'
    if (!window.confirm(`${verb} ${cinema.name}? ${cinema.is_active ? 'Its unbooked shows are removed; booked shows stay.' : 'A weekly programme is created for it.'}`)) return
    setBusyId(cinema.id)
    try {
      const updated = await adminSetCinemaActive(cinema.id, !cinema.is_active)
      setCinemas(current => current.map(item => (item.id === updated.id ? updated : item)))
      setToast(`${updated.name} is now ${updated.is_active ? 'on' : 'off'} (${updated.upcoming_shows} upcoming shows).`)
      setReload(value => value + 1)
    } catch (requestError) {
      setToast(requestError.message)
    } finally {
      setBusyId(null)
    }
  }

  async function confirmCancel(reason) {
    setBusy(true)
    try {
      const result = await adminCancelShow(cancelShow.id, reason)
      setToast(`Show cancelled. ${result.cancelled_bookings} booking${result.cancelled_bookings === 1 ? '' : 's'} refunded.`)
      setCancelShow(null)
      setReload(value => value + 1)
    } catch (requestError) {
      setToast(requestError.message)
    } finally {
      setBusy(false)
    }
  }

  const selected = cinemas?.find(cinema => cinema.id === selectedId)
  const byScreen = useMemo(() => {
    const groups = new Map()
    for (const show of shows || []) {
      if (!groups.has(show.screen_name)) groups.set(show.screen_name, [])
      groups.get(show.screen_name).push(show)
    }
    return [...groups.entries()]
  }, [shows])

  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">VENUES</span><h1 className="admin-title">Cinemas & shows</h1></div>
      </div>
      {error ? <ErrorState message={error} /> : !cinemas ? <p className="muted">Loading cinemas…</p> : (
        <div className="admin-split">
          <ul className="cinema-picker" aria-label="Cinemas">
            {cinemas.map(cinema => (
              <li key={cinema.id} className={cinema.id === selectedId ? 'active' : ''}>
                <button type="button" onClick={() => { setSelectedId(cinema.id); setShows(null) }}>
                  <strong>{cinema.name}</strong>
                  <small>{cinema.area} · {cinema.screens_count} screens · {cinema.upcoming_shows} shows</small>
                </button>
                {can('cinemas.manage') && (
                  <label className="switch" title={cinema.is_active ? 'Showing on CineBook' : 'Hidden'}>
                    <input type="checkbox" checked={cinema.is_active} disabled={busyId === cinema.id} onChange={() => toggle(cinema)}
                           aria-label={`${cinema.name} is on CineBook`} />
                    <span aria-hidden="true" />
                  </label>
                )}
              </li>
            ))}
          </ul>
          <section className="panel admin-card">
            {!selected ? <p className="muted">Choose a cinema.</p> : (
              <>
                <h2>{selected.name} <small>{selected.chain} · {selected.seats_total.toLocaleString('en-IN')} seats · {selected.bookings_7_days} bookings in 7 days</small></h2>
                {!selected.is_active && <p className="admin-note">This cinema is switched off: customers cannot see or book it.</p>}
                <DayTabs days={days} value={day} onChange={next => { setDay(next); setShows(null) }} />
                {!shows ? <p className="muted">Loading shows…</p> : shows.length === 0 ? <p className="muted">No shows on this day.</p> : (
                  byScreen.map(([screen, rows]) => (
                    <div className="screen-block" key={screen}>
                      <h3>{screen} <small>{rows[0].screen_format}</small></h3>
                      <div className="table-wrap">
                        <table className="admin-table compact">
                          <thead><tr><th>Time</th><th>Movie</th><th>Sold</th><th>Occupancy</th><th>Revenue</th><th>Status</th><th /></tr></thead>
                          <tbody>
                            {rows.map(show => {
                              const pct = show.seats_total ? Math.round((show.seats_sold / show.seats_total) * 100) : 0
                              const future = new Date(show.start_time).getTime() > Date.now()
                              return (
                                <tr key={show.id}>
                                  <td>{formatTime(show.start_time)}</td>
                                  <td>{show.movie_title}</td>
                                  <td>{show.seats_sold}/{show.seats_total}</td>
                                  <td><div className="occupancy" aria-label={`${pct}% sold`}><div style={{ width: `${pct}%` }} /></div><small>{pct}%</small></td>
                                  <td>{money(show.revenue)}</td>
                                  <td><StatusPill status={show.status} />{show.cancelled_reason && <small>{show.cancelled_reason}</small>}</td>
                                  <td>{can('shows.manage') && show.status === 'SCHEDULED' && future && (
                                    <button type="button" className="link-button danger-link" onClick={() => setCancelShow(show)}>Cancel show</button>
                                  )}</td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ))
                )}
              </>
            )}
          </section>
        </div>
      )}
      <ReasonDialog open={Boolean(cancelShow)} busy={busy} confirmLabel="Cancel show & refund all"
                    title={cancelShow ? `Cancel ${cancelShow.movie_title} at ${formatTime(cancelShow.start_time)}?` : ''}
                    message={cancelShow ? `${cancelShow.bookings} confirmed booking${cancelShow.bookings === 1 ? '' : 's'} will be cancelled and refunded, and customers are emailed. The show can no longer be booked.` : ''}
                    onConfirm={confirmCancel} onClose={() => setCancelShow(null)} />
      <Toast message={toast} />
    </div>
  )
}

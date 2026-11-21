import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminDashboard } from '../../api'
import ErrorState from '../../components/ErrorState'
import { money } from '../../utils/format'
import { STATUS_LABEL, StatusPill, shortDateTime } from './ui'

const PERIODS = [7, 30, 90]

function Kpi({ label, value, hint }) {
  return (
    <div className="kpi">
      <small>{label}</small>
      <strong>{value}</strong>
      {hint && <span>{hint}</span>}
    </div>
  )
}

// Daily revenue: one series, one hue, thin bars with rounded tops on a shared baseline, hover tooltip per bar.
function RevenueChart({ points }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(1, ...points.map(point => Number(point.revenue)))
  const step = max <= 5000 ? 1000 : max <= 20000 ? 5000 : max <= 100000 ? 20000 : 50000
  const top = Math.ceil(max / step) * step || step
  const ticks = Array.from({ length: Math.min(5, top / step) + 1 }, (_, index) => (top / Math.min(5, top / step)) * index)
  const dayLabel = value => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' }).format(new Date(`${value}T12:00:00+05:30`))
  const labelEvery = Math.ceil(points.length / 8)

  return (
    <figure className="chart">
      <div className="chart-plot" onMouseLeave={() => setHover(null)}>
        <div className="chart-grid" aria-hidden="true">
          {ticks.slice().reverse().map(tick => <div key={tick}><span>{tick >= 1000 ? `₹${tick / 1000}k` : `₹${tick}`}</span></div>)}
        </div>
        <div className="chart-bars" role="img" aria-label={`Daily revenue for the last ${points.length} days`}>
          {points.map((point, index) => {
            const value = Number(point.revenue)
            return (
              <div className="chart-col" key={point.date} onMouseEnter={() => setHover(index)} onFocus={() => setHover(index)} tabIndex={0}
                   aria-label={`${dayLabel(point.date)}: ${money(value)}, ${point.bookings} bookings`}>
                <div className={`chart-bar ${hover === index ? 'active' : ''}`} style={{ height: `${(value / top) * 100}%` }} />
                {index % labelEvery === 0 && <small>{dayLabel(point.date)}</small>}
              </div>
            )
          })}
        </div>
        {hover !== null && (
          <div className="chart-tooltip" style={{ left: `${((hover + 0.5) / points.length) * 100}%` }}>
            <strong>{dayLabel(points[hover].date)}</strong>
            <span>{money(points[hover].revenue)}</span>
            <small>{points[hover].bookings} bookings · {points[hover].tickets} tickets</small>
          </div>
        )}
      </div>
      <details className="chart-table">
        <summary>Show as table</summary>
        <table>
          <thead><tr><th>Date</th><th>Revenue</th><th>Bookings</th><th>Tickets</th></tr></thead>
          <tbody>{points.map(point => <tr key={point.date}><td>{dayLabel(point.date)}</td><td>{money(point.revenue)}</td><td>{point.bookings}</td><td>{point.tickets}</td></tr>)}</tbody>
        </table>
      </details>
    </figure>
  )
}

// Top five by tickets: horizontal bars in the same single hue, value in text ink beside each.
function Ranking({ title, rows, empty }) {
  const max = Math.max(1, ...rows.map(row => row.tickets))
  return (
    <section className="panel admin-card">
      <h2>{title}</h2>
      {rows.length === 0 ? <p className="muted">{empty}</p> : (
        <ol className="ranking">
          {rows.map(row => (
            <li key={row.id}>
              <div className="ranking-label"><span>{row.name}</span><small>{row.tickets} tickets · {money(row.revenue)}</small></div>
              <div className="ranking-track"><div style={{ width: `${(row.tickets / max) * 100}%` }} /></div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export default function Dashboard({ onSignOut }) {
  const [days, setDays] = useState(7)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    adminDashboard(days)
      .then(result => { if (active) { setData(result); setError('') } })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 401) onSignOut()
        else setError(requestError.message)
      })
    return () => { active = false }
  }, [days, onSignOut])

  const k = data?.kpis
  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">OVERVIEW</span><h1 className="admin-title">Dashboard</h1></div>
        <div className="segmented" role="group" aria-label="Period">
          {PERIODS.map(period => (
            <button type="button" key={period} aria-pressed={days === period} className={days === period ? 'active' : ''} onClick={() => setDays(period)}>
              {period} days
            </button>
          ))}
        </div>
      </div>
      {error ? <ErrorState message={error} /> : !data ? <p className="muted">Loading dashboard…</p> : (
        <>
          <div className="kpi-grid">
            <Kpi label="Revenue today" value={money(k.revenue_today)} hint={`${k.bookings_today} bookings · ${k.tickets_today} tickets`} />
            <Kpi label={`Revenue, last ${days} days`} value={money(k.revenue_period)} hint={`Average order ${money(k.average_order)}`} />
            <Kpi label={`Tickets, last ${days} days`} value={k.tickets_period.toLocaleString('en-IN')} hint={`${k.bookings_period} bookings`} />
            <Kpi label="Occupancy, next 7 days" value={`${k.occupancy_next_7_days_pct}%`} hint={`${k.upcoming_shows_7_days.toLocaleString('en-IN')} shows scheduled`} />
            <Kpi label={`Cancellations, last ${days} days`} value={k.cancellations_period} hint={`${money(k.refunded_period)} refunded`} />
            <Kpi label="Customers" value={k.customers_total} hint={`${k.new_customers_period} new in ${days} days`} />
            <Kpi label="Films showing" value={k.active_films} hint={`${k.active_cinemas} cinemas`} />
          </div>

          <section className="panel admin-card">
            <h2>Revenue by day <small>confirmed bookings, by booking date</small></h2>
            <RevenueChart points={data.revenue_by_day} />
          </section>

          <div className="admin-two">
            <Ranking title={`Top films, last ${days} days`} rows={data.top_films} empty="No tickets sold in this period yet." />
            <Ranking title={`Top cinemas, last ${days} days`} rows={data.top_cinemas} empty="No tickets sold in this period yet." />
          </div>

          <div className="admin-two">
            <section className="panel admin-card">
              <h2>Bookings by status <small>last {days} days</small></h2>
              <div className="status-grid">
                {['CONFIRMED', 'PENDING', 'CANCELLED', 'FAILED'].map(status => (
                  <div key={status}><StatusPill status={status} /><strong>{data.status_breakdown[status] || 0}</strong><small>{STATUS_LABEL[status]}</small></div>
                ))}
              </div>
            </section>
            <section className="panel admin-card">
              <h2>Latest bookings <Link to="/admin/bookings" className="card-link">All bookings →</Link></h2>
              <ul className="recent-list">
                {data.recent_bookings.map(booking => (
                  <li key={booking.booking_ref}>
                    <div><strong>{booking.booking_ref}</strong><small>{booking.customer_name} · {booking.movie_title} · {booking.cinema_name}</small></div>
                    <div className="recent-right"><StatusPill status={booking.status} /><small>{money(booking.total_amount)} · {shortDateTime(booking.created_at)}</small></div>
                  </li>
                ))}
                {data.recent_bookings.length === 0 && <li className="muted">No bookings yet.</li>}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  )
}

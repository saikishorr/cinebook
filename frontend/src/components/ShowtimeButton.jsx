import { Link } from 'react-router-dom'
import { fillLevel, formatTime, money } from '../utils/format'

const FILL_TEXT = { ok: 'Available', filling: 'Filling fast', almost: 'Almost full' }

// One showtime. `compact` is the small pill used inside a cinema's row of times.
export default function ShowtimeButton({ show, compact = false }) {
  const level = fillLevel(show)
  const soldOut = show.seats_total > 0 && show.seats_available === 0
  const format = show.screen_format && show.screen_format !== '2D' ? show.screen_format : null
  const title = `${formatTime(show.start_time)} · ${show.screen_name}${format ? ` · ${format}` : ''} · ` +
    `${soldOut ? 'Sold out' : `${show.seats_available} of ${show.seats_total} seats left`} · from ${money(show.regular_price)}`

  if (compact) {
    return soldOut ? (
      <span className="time-pill sold-out" title={title}>{formatTime(show.start_time)}<small>Sold out</small></span>
    ) : (
      <Link className={`time-pill fill-${level}`} to={`/shows/${show.id}`} title={title} aria-label={title}>
        {formatTime(show.start_time)}
        <small>{format || FILL_TEXT[level]}</small>
      </Link>
    )
  }

  return (
    <Link className={`showtime fill-${level}`} to={`/shows/${show.id}`} title={title}>
      <strong>{formatTime(show.start_time)}</strong>
      <span>{show.screen_name}{format ? ` · ${format}` : ''}</span>
      <small>from {money(show.regular_price)}{show.seats_total ? ` · ${FILL_TEXT[level]}` : ''}</small>
      <b>→</b>
    </Link>
  )
}

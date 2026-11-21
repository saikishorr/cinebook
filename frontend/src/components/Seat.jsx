import { money } from '../utils/format'

const TYPE_NAMES = { REGULAR: 'regular', PREMIUM: 'prime', RECLINER: 'recliner' }

export default function Seat({ seat, selected, onToggle }) {
  const status = String(seat.status).toUpperCase()
  const type = TYPE_NAMES[seat.seat_type] || 'regular'
  const label = `${seat.row_label}${seat.seat_number}`
  const extra = seat.accessible ? ', wheelchair accessible' : ''

  return (
    <button
      type="button"
      aria-label={`${label}, ${selected ? 'selected' : status.toLowerCase()}, ${type}${extra}, ${money(seat.price)}`}
      aria-pressed={selected}
      disabled={status !== 'AVAILABLE'}
      onClick={() => onToggle(seat)}
      className={`seat ${selected ? 'selected' : ''} ${status.toLowerCase()} ${type === 'regular' ? '' : type} ${type === 'prime' ? 'premium' : ''} ${seat.accessible ? 'accessible' : ''}`}
      title={`${label} · ${type[0].toUpperCase()}${type.slice(1)}${seat.accessible ? ' · Wheelchair accessible' : ''} · ${money(seat.price)}`}
    >
      {seat.accessible && status === 'AVAILABLE' && !selected ? '♿' : seat.seat_number}
    </button>
  )
}

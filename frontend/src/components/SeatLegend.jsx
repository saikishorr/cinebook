import { money } from '../utils/format'

const SECTION_CLASS = { REGULAR: 'available', PREMIUM: 'premium', RECLINER: 'recliner' }

// Prices per section (from the API), then the seat states.
export default function SeatLegend({ sections = [], prices = {}, hasAccessible = false }) {
  const types = sections.length
    ? sections.map(section => [SECTION_CLASS[section.seat_type] || 'available', `${section.name} · ${money(section.price)}`])
    : [
        ['available', prices.regular != null ? `Regular · ${money(prices.regular)}` : 'Available'],
        ['premium', prices.premium != null ? `Premium · ${money(prices.premium)}` : 'Premium'],
      ]
  const states = [['selected', 'Selected'], ['held', 'Held'], ['booked', 'Booked']]
  return (
    <div className="seat-legend">
      {[...types, ...states].map(([type, label]) => (
        <span key={`${type}-${label}`}>
          <i className={`legend-seat ${type}`} />
          {label}
        </span>
      ))}
      {hasAccessible && <span><i className="legend-seat accessible">♿</i>Wheelchair accessible</span>}
    </div>
  )
}

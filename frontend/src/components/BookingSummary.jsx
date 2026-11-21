import { money } from '../utils/format'

export default function BookingSummary({ seats, total, holding, onHold, signedIn = true }) {
  return (
    <aside className="booking-summary">
      <span className="eyebrow">YOUR SELECTION</span>
      <h2>{seats.length ? `${seats.length} ${seats.length === 1 ? 'seat' : 'seats'}` : 'Choose your seats'}</h2>
      <p className="chosen-seats">
        {seats.map(seat => `${seat.row_label}${seat.seat_number}`).join(' · ') || 'Your seats will appear here'}
      </p>
      <div className="summary-total">
        <span>Total</span>
        <strong>{money(total)}</strong>
      </div>
      <button className="button primary full" disabled={!seats.length || holding} onClick={onHold}>
        {holding ? 'Holding…' : signedIn ? 'Hold seats' : 'Sign in to book'} <span>→</span>
      </button>
      <small>Seats are held for a limited time at checkout.</small>
    </aside>
  )
}

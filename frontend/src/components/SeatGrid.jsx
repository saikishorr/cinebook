import { money } from '../utils/format'
import Seat from './Seat'

// Draws the hall as the layout file defines it: every seat at its row_index / col, so aisles,
// cross-aisles and staggered rows appear where they are in the hall. Front row (nearest the screen) on top.
// Each section ("Recliner ₹450") is labelled above its first row, as cinemas do on their seat plans.
export default function SeatGrid({ seats, grid, sections, selectedIds, onToggle }) {
  const byRow = new Map()
  for (const seat of seats) {
    if (!byRow.has(seat.row_index)) byRow.set(seat.row_index, [])
    byRow.get(seat.row_index).push(seat)
  }
  const sectionOfRow = new Map()
  for (const section of sections || []) for (const label of section.row_labels) sectionOfRow.set(label, section)

  const rows = []
  let lastSection = null
  for (let index = 0; index < grid.rows; index++) {
    const rowSeats = byRow.get(index)
    if (!rowSeats) {                                     // a cross-aisle: an empty row in the layout
      rows.push(<div className="grid-row grid-gap" key={`gap-${index}`} aria-hidden="true" />)
      continue
    }
    const label = rowSeats[0].row_label
    const section = sectionOfRow.get(label)
    if (section && section !== lastSection) {
      rows.push(
        <div className="grid-section" key={`section-${index}`}>
          <span>{section.name}</span><b>{money(section.price)}</b>
        </div>,
      )
      lastSection = section
    }
    const byCol = new Map(rowSeats.map(seat => [seat.col, seat]))
    rows.push(
      <div className="grid-row" role="group" aria-label={`Row ${label}`} key={label}
           style={{ gridTemplateColumns: `22px repeat(${grid.cols}, var(--seat-size)) 22px` }}>
        <b className="row-label">{label}</b>
        {Array.from({ length: grid.cols }, (_, col) => {
          const seat = byCol.get(col + 1)
          return seat
            ? <Seat key={seat.id} seat={seat} selected={selectedIds.includes(seat.id)} onToggle={onToggle} />
            : <span key={`aisle-${col}`} className="aisle" aria-hidden="true" />
        })}
        <b className="row-label right">{label}</b>
      </div>,
    )
  }
  return <div className="seat-grid">{rows}</div>
}

import { dayLabel, formatDate } from '../utils/format'

// A row of day buttons ("Today", "Tomorrow", "Sun 23 Nov", ...). `days` are YYYY-MM-DD strings.
export default function DayTabs({ days, value, onChange }) {
  return (
    <div className="day-tabs" role="tablist" aria-label="Show dates">
      {days.map(day => {
        const label = dayLabel(day)
        const date = formatDate(`${day}T12:00:00+05:30`)
        return (
          <button type="button" role="tab" key={day} aria-selected={day === value}
                  className={`day-tab ${day === value ? 'active' : ''}`} onClick={() => onChange(day)}>
            <strong>{label}</strong>
            <small>{label === date ? new Intl.DateTimeFormat('en-IN', { weekday: 'long', timeZone: 'Asia/Kolkata' }).format(new Date(`${day}T12:00:00+05:30`)) : date}</small>
          </button>
        )
      })}
    </div>
  )
}

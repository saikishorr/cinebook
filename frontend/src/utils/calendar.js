// Builds an .ics calendar file for a booking, so the customer can add the show to their calendar.
function stamp(date) {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
}

function escape(text) {
  return String(text).replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/([,;])/g, '\\$1')
}

export function downloadBookingCalendar(booking, durationMinutes = 150) {
  const start = new Date(booking.start_time)
  const end = new Date(start.getTime() + durationMinutes * 60000)
  const seats = (booking.seats || []).map(seat => `${seat.row_label}${seat.seat_number}`).join(', ')
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//CineBook//Booking//EN', 'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${booking.booking_ref}@cinebook`,
    `DTSTAMP:${stamp(new Date())}`,
    `DTSTART:${stamp(start)}`,
    `DTEND:${stamp(end)}`,
    `SUMMARY:${escape(`${booking.movie_title} · CineBook`)}`,
    `LOCATION:${escape(`CineBook ${booking.screen_name}`)}`,
    `DESCRIPTION:${escape(`Booking ${booking.booking_ref}\nSeats: ${seats}\nPlease arrive 20 minutes early.`)}`,
    'BEGIN:VALARM', 'TRIGGER:-PT1H', 'ACTION:DISPLAY', `DESCRIPTION:${escape(`${booking.movie_title} starts in 1 hour`)}`, 'END:VALARM',
    'END:VEVENT', 'END:VCALENDAR',
  ]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `cinebook-${booking.booking_ref}.ics`
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

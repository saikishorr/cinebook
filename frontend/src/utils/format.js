const dateFormatter = new Intl.DateTimeFormat('en-IN', {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  timeZone: 'Asia/Kolkata',
})

const timeFormatter = new Intl.DateTimeFormat('en-IN', {
  hour: 'numeric',
  minute: '2-digit',
  timeZone: 'Asia/Kolkata',
})

export function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
  }).format(Number(value) || 0)
}

export function formatDate(value) {
  return dateFormatter.format(new Date(value))
}

export function formatTime(value) {
  return timeFormatter.format(new Date(value))
}

export function formatCountdown(seconds) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

const dayKeyFormatter = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' })

/** The cinema's calendar day (India time) as YYYY-MM-DD, for grouping shows by day. */
export function dayKey(value) {
  return dayKeyFormatter.format(new Date(value))
}

/** "Today", "Tomorrow" or "Sat 22 Nov", in India time. */
export function relativeDay(value) {
  const key = dayKey(value)
  const today = dayKey(Date.now())
  const tomorrow = dayKey(Date.now() + 86400000)
  if (key === today) return 'Today'
  if (key === tomorrow) return 'Tomorrow'
  return formatDate(value)
}

/** The next `count` cinema days (India time) as YYYY-MM-DD, starting today. */
export function nextDays(count = 8) {
  return Array.from({ length: count }, (_, index) => dayKey(Date.now() + index * 86400000))
}

/** A YYYY-MM-DD day as "Today", "Tomorrow" or "Sat 22 Nov". Noon avoids any time-zone edge. */
export function dayLabel(key) {
  return relativeDay(`${key}T12:00:00+05:30`)
}

/** How full a show is, for colouring showtimes: 'ok', 'filling' (under 40% left) or 'almost' (under 15%). */
export function fillLevel(show) {
  if (!show.seats_total) return 'ok'
  const left = show.seats_available / show.seats_total
  return left < 0.15 ? 'almost' : left < 0.4 ? 'filling' : 'ok'
}

/** A map link for a cinema (OpenStreetMap, no API key). */
export function mapLink(latitude, longitude) {
  return `https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=17/${latitude}/${longitude}`
}

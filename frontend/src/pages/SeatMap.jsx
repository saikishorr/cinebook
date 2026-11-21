import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { cancelHold, createHold, getSeats, getShow } from '../api'
import BookingSummary from '../components/BookingSummary'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import Seat from '../components/Seat'
import SeatGrid from '../components/SeatGrid'
import SeatLegend from '../components/SeatLegend'
import Shell from '../components/Shell'
import Toast from '../components/Toast'
import { useAuth } from '../auth'
import { clearActiveHold, readActiveHold, saveActiveHold } from '../utils/activeHold'
import { formatDate, formatTime } from '../utils/format'
import { useDocumentTitle, useVisibleInterval } from '../utils/hooks'

const MAX_SEATS = 10
const PENDING_KEY = 'cinebook_pending_seats'
const POLL_MS = 10000

export default function SeatMap() {
  const { showId } = useParams()
  const navigate = useNavigate()
  const [show, setShow] = useState(null)
  const [seats, setSeats] = useState([])
  const [layout, setLayout] = useState({ grid: null, sections: [] })   // the hall's shape, from the layout file
  const [selectedIds, setSelectedIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [holding, setHolding] = useState(false)
  const [activeHold] = useState(readActiveHold)
  const { user, expired } = useAuth()
  useDocumentTitle(show ? `Seats · ${show.movie_title}` : 'Pick your seats')

  const load = useCallback(() => {
    let active = true
    Promise.all([getShow(showId), getSeats(showId)])
      .then(([showData, seatData]) => {
        if (!active) return
        setShow(showData)
        setSeats(seatData.seats)
        // Back from signing in: restore the seats that were chosen, if they are still free.
        try {
          const pending = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null')
          sessionStorage.removeItem(PENDING_KEY)
          if (pending && String(pending.showId) === String(showId)) {
            const free = new Set(seatData.seats.filter(seat => seat.status === 'AVAILABLE').map(seat => seat.id))
            setSelectedIds(pending.ids.filter(id => free.has(id)).slice(0, MAX_SEATS))
          }
        } catch { /* ignore */ }
        setLayout({ grid: seatData.grid || null, sections: seatData.sections || [] })
      })
      .catch(requestError => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [showId])

  useEffect(() => load(), [load])

  function retry() {
    setLoading(true)
    setError('')
    load()
  }

  // A mirror of the selection, so the poll can compare without side effects inside a state updater.
  const selectedRef = useRef(selectedIds)
  useEffect(() => { selectedRef.current = selectedIds }, [selectedIds])

  // Reload seat states and drop any selected seat someone else has taken in the meantime.
  const refreshSeats = useCallback(async ({ notify = false } = {}) => {
    const { seats: latest } = await getSeats(showId)
    const available = new Set(latest.filter(seat => seat.status === 'AVAILABLE').map(seat => seat.id))
    const kept = selectedRef.current.filter(id => available.has(id))
    if (notify && kept.length < selectedRef.current.length) setToast('A selected seat is no longer available and was removed.')
    setSeats(latest)
    setSelectedIds(kept)
  }, [showId])

  const poll = useCallback(() => { refreshSeats({ notify: true }).catch(() => {}) }, [refreshSeats])

  useVisibleInterval(poll, POLL_MS)

  useEffect(() => {
    if (!toast) return undefined
    const timeoutId = setTimeout(() => setToast(''), 3500)
    return () => clearTimeout(timeoutId)
  }, [toast])

  const rows = useMemo(() => {
    const grouped = new Map()
    for (const seat of seats) {
      if (!grouped.has(seat.row_label)) grouped.set(seat.row_label, [])
      grouped.get(seat.row_label).push(seat)
    }
    return [...grouped.entries()]
      .sort(([left], [right]) => left.localeCompare(right, undefined, { numeric: true }))
      .map(([row, rowSeats]) => [row, [...rowSeats].sort((a, b) => a.seat_number - b.seat_number)])
  }, [seats])

  const prices = useMemo(() => {
    const find = type => seats.find(seat => seat.seat_type === type)?.price
    return { regular: find('REGULAR'), premium: find('PREMIUM') }
  }, [seats])

  const selectedSeats = selectedIds.map(id => seats.find(seat => seat.id === id)).filter(Boolean)
  const total = selectedSeats.reduce((sum, seat) => sum + Number(seat.price), 0)
  const holdForThisShow = activeHold && String(activeHold.show_id) === String(showId) ? activeHold : null

  function toggleSeat(seat) {
    if (selectedIds.includes(seat.id)) {
      setSelectedIds(selectedIds.filter(id => id !== seat.id))
    } else if (selectedIds.length >= MAX_SEATS) {
      setToast(`You can select up to ${MAX_SEATS} seats.`)
    } else {
      setSelectedIds([...selectedIds, seat.id])
    }
  }

  // Signing in leaves this page; remember the chosen seats so they are still selected on return.
  function sendToSignIn() {
    try { sessionStorage.setItem(PENDING_KEY, JSON.stringify({ showId, ids: selectedIds })) } catch { /* ignore */ }
    navigate(`/login?next=${encodeURIComponent(`/shows/${showId}`)}`)
  }

  async function holdSeats() {
    if (!user) return sendToSignIn()
    setHolding(true)
    try {
      // Starting over on this show: give back the seats held earlier so they don't stay blocked.
      if (holdForThisShow) {
        await cancelHold(holdForThisShow.hold_id).catch(() => {})
        clearActiveHold()
      }
      const result = await createHold(showId, selectedIds)
      saveActiveHold(result)
      navigate(`/checkout/${result.hold_id}`)
    } catch (requestError) {
      if (requestError.status === 401) {
        expired()
        sendToSignIn()
      } else if (requestError.status === 409) {
        setSelectedIds([])
        setToast('Some of those seats were just taken by someone else.')
        await refreshSeats().catch(() => {})
      } else if (requestError.status === 503) {
        setToast('Seat holds are temporarily unavailable. Please try again in a moment.')
      } else {
        setToast(requestError.message)
      }
    } finally {
      setHolding(false)
    }
  }

  return (
    <Shell>
      {loading ? <LoadingState /> : error ? <ErrorState message={error} onRetry={retry} /> : (
        <>
          <Link className="back-link" to={`/movies/${show.movie_id}`}>← <span>Back to showtimes</span></Link>
          <div className="section-heading seat-title">
            <div>
              <span className="eyebrow">YOUR CINEMA, YOUR MOMENT</span>
              <h1>Pick your seats<span className="accent">.</span></h1>
              <p>{show.movie_title} <span>·</span> {formatDate(show.start_time)} · {formatTime(show.start_time)}</p>
              {show.cinema_name && (
                <p className="seat-venue"><Link to={`/cinemas/${show.cinema_id}`}>{show.cinema_name}</Link> <span>·</span> {show.cinema_area} <span>·</span> {show.screen_name}{show.screen_format && show.screen_format !== '2D' ? ` · ${show.screen_format}` : ''}</p>
              )}
            </div>
          </div>
          {holdForThisShow && (
            <Link className="hold-banner" to={`/checkout/${holdForThisShow.hold_id}`}>
              You have seats on hold — <b>Continue to checkout →</b>
            </Link>
          )}
          {seats.length === 0 ? <EmptyState>No seats are listed for this show.</EmptyState> : (
            <div className="seat-layout">
              <section className="seat-area">
                <div className="screen-wrap"><div className="screen-curve" /><span>SCREEN</span></div>
                <div className="seat-scroll">
                  {layout.grid ? (
                    <SeatGrid seats={seats} grid={layout.grid} sections={layout.sections} selectedIds={selectedIds} onToggle={toggleSeat} />
                  ) : (
                  <div className="seat-rows">
                    {rows.map(([row, rowSeats]) => (
                      <div className="seat-row" key={row} role="group" aria-label={`Row ${row}`}>
                        <b className="row-label">{row}</b>
                        {rowSeats.map(seat => (
                          <Seat key={seat.id} seat={seat} selected={selectedIds.includes(seat.id)} onToggle={toggleSeat} />
                        ))}
                      </div>
                    ))}
                  </div>
                  )}
                </div>
                <SeatLegend sections={layout.sections} prices={prices} hasAccessible={seats.some(seat => seat.accessible)} />
              </section>
              <BookingSummary seats={selectedSeats} total={total} holding={holding} onHold={holdSeats} signedIn={Boolean(user)} />
            </div>
          )}
          <Toast message={toast} />
        </>
      )}
    </Shell>
  )
}

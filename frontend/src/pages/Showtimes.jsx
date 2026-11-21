import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getMovie, getMovieShowDates, getMovieShows } from '../api'
import DayTabs from '../components/DayTabs'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import Poster from '../components/Poster'
import ShowtimeButton from '../components/ShowtimeButton'
import Shell from '../components/Shell'
import { useDocumentTitle } from '../utils/hooks'

const ALL_AREAS = ''

// Group one day's shows by cinema: [{ id, name, area, chain, shows: [...] }], cinemas A–Z.
function byCinema(shows) {
  const cinemas = new Map()
  for (const show of shows) {
    if (!cinemas.has(show.cinema_id)) {
      cinemas.set(show.cinema_id, { id: show.cinema_id, name: show.cinema_name, area: show.cinema_area, chain: show.cinema_chain, shows: [] })
    }
    cinemas.get(show.cinema_id).shows.push(show)
  }
  for (const cinema of cinemas.values()) cinema.shows.sort((a, b) => a.start_time.localeCompare(b.start_time))
  return [...cinemas.values()].sort((a, b) => a.name.localeCompare(b.name))
}

export default function Showtimes() {
  const { movieId } = useParams()
  const [movie, setMovie] = useState(null)
  const [days, setDays] = useState([])
  const [day, setDay] = useState(null)
  const [shows, setShows] = useState([])
  const [loading, setLoading] = useState(true)
  const [showsLoading, setShowsLoading] = useState(true)
  const [error, setError] = useState('')
  const [notFound, setNotFound] = useState(false)
  const [area, setArea] = useState(ALL_AREAS)
  useDocumentTitle(movie?.title || 'Showtimes')

  const load = useCallback(() => {
    let active = true
    Promise.all([getMovie(movieId), getMovieShowDates(movieId)])
      .then(([movieData, dates]) => {
        if (!active) return
        setMovie(movieData)
        setDays(dates)
        setDay(dates[0] || null)
      })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 404) setNotFound(true)
        else setError(requestError.message)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [movieId])

  useEffect(() => load(), [load])

  function retry() {
    setLoading(true)
    setError('')
    load()
  }

  // Fetch the chosen day's shows; the area filter is applied on the page.
  useEffect(() => {
    if (!day) return undefined
    let active = true
    getMovieShows(movieId, { date: day })
      .then(data => { if (active) setShows(data) })
      .catch(requestError => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setShowsLoading(false) })
    return () => { active = false }
  }, [movieId, day])

  function chooseDay(next) {
    if (next === day) return
    setShowsLoading(true)
    setDay(next)
  }

  const cinemas = useMemo(() => byCinema(shows), [shows])
  const areas = useMemo(() => [...new Set(cinemas.map(cinema => cinema.area))].sort(), [cinemas])
  const visible = area ? cinemas.filter(cinema => cinema.area === area) : cinemas

  return (
    <Shell>
      <Link className="back-link" to="/">← <span>All movies</span></Link>
      {loading ? <LoadingState /> : error && !movie ? <ErrorState message={error} onRetry={retry} /> : notFound || !movie ? (
        <EmptyState title="Movie not found">This movie is not showing in Pune right now.</EmptyState>
      ) : (
        <>
          <section className={`detail-hero ${movie.backdrop_url ? 'has-backdrop' : ''}`}
                   style={movie.backdrop_url ? { '--backdrop': `url("${movie.backdrop_url}")` } : undefined}>
            <Poster movie={movie} large />
            <div className="detail-copy">
              <span className="eyebrow">NOW SHOWING IN PUNE</span>
              <h1>{movie.title}</h1>
              <div className="detail-meta">
                {[movie.language, movie.certificate, movie.duration_minutes && `${movie.duration_minutes} min`, ...(movie.genres || [])]
                  .filter(Boolean).map(value => <span key={value}>{value}</span>)}
              </div>
              {movie.description && <p>{movie.description}</p>}
              {movie.trailer_url && (
                <a className="button trailer-button" href={movie.trailer_url} target="_blank" rel="noopener noreferrer">▶ Watch trailer</a>
              )}
            </div>
          </section>

          <div className="section-heading show-heading">
            <div><span className="eyebrow">MAKE IT A MOVIE NIGHT</span><h2>Choose a cinema and showtime</h2></div>
            {movie.cinemas_count > 0 && <span className="muted">Playing at {movie.cinemas_count} Pune cinemas</span>}
          </div>

          {days.length === 0 ? <EmptyState>No upcoming shows are scheduled for this movie.</EmptyState> : (
            <>
              <DayTabs days={days} value={day} onChange={chooseDay} />
              {areas.length > 1 && (
                <div className="filter-bar">
                  <label className="select-field">
                    <span>Area</span>
                    <select value={area} onChange={event => setArea(event.target.value)}>
                      <option value={ALL_AREAS}>All of Pune ({cinemas.length} cinemas)</option>
                      {areas.map(item => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </label>
                  <span className="fill-legend"><i className="fill-ok" />Available <i className="fill-filling" />Filling fast <i className="fill-almost" />Almost full</span>
                </div>
              )}
              {error && <ErrorState message={error} />}
              {showsLoading ? <LoadingState /> : visible.length === 0 ? (
                <EmptyState>No shows for this movie on this day{area ? ` in ${area}` : ''}.</EmptyState>
              ) : (
                <div className="cinema-list">
                  {visible.map(cinema => (
                    <article className="cinema-row" key={cinema.id}>
                      <div className="cinema-row-head">
                        <Link to={`/cinemas/${cinema.id}`} className="cinema-name">{cinema.name}</Link>
                        <small>{cinema.area} · {cinema.chain}</small>
                      </div>
                      <div className="time-pills">
                        {cinema.shows.map(show => <ShowtimeButton show={show} compact key={show.id} />)}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </Shell>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getCinema, getCinemaShows } from '../api'
import DayTabs from '../components/DayTabs'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import ShowtimeButton from '../components/ShowtimeButton'
import Shell from '../components/Shell'
import { mapLink, nextDays } from '../utils/format'
import { useDocumentTitle } from '../utils/hooks'

// One cinema: every film it shows on the chosen day.
export default function CinemaDetail() {
  const { cinemaId } = useParams()
  const days = useMemo(() => nextDays(8), [])
  const [day, setDay] = useState(days[0])
  const [cinema, setCinema] = useState(null)
  const [shows, setShows] = useState([])
  const [loading, setLoading] = useState(true)
  const [showsLoading, setShowsLoading] = useState(true)
  const [error, setError] = useState('')
  const [notFound, setNotFound] = useState(false)
  useDocumentTitle(cinema?.name || 'Cinema')

  useEffect(() => {
    let active = true
    getCinema(cinemaId)
      .then(data => { if (active) setCinema(data) })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 404) setNotFound(true)
        else setError(requestError.message)
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [cinemaId])

  useEffect(() => {
    let active = true
    getCinemaShows(cinemaId, day)
      .then(data => { if (active) setShows(data) })
      .catch(requestError => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setShowsLoading(false) })
    return () => { active = false }
  }, [cinemaId, day])

  function chooseDay(next) {
    if (next === day) return
    setShowsLoading(true)
    setDay(next)
  }

  // [{ movie_id, title, shows: [...] }], films A–Z.
  const films = useMemo(() => {
    const grouped = new Map()
    for (const show of shows) {
      if (!grouped.has(show.movie_id)) grouped.set(show.movie_id, { movie_id: show.movie_id, title: show.movie_title, shows: [] })
      grouped.get(show.movie_id).shows.push(show)
    }
    return [...grouped.values()].sort((a, b) => a.title.localeCompare(b.title))
  }, [shows])

  return (
    <Shell>
      <Link className="back-link" to="/cinemas">← <span>All cinemas</span></Link>
      {loading ? <LoadingState /> : notFound ? (
        <EmptyState title="Cinema not found">This cinema is not listed on CineBook.</EmptyState>
      ) : !cinema ? <ErrorState message={error} /> : (
        <>
          <section className="cinema-hero panel">
            <span className="eyebrow">{cinema.chain.toUpperCase()} · {cinema.area.toUpperCase()}</span>
            <h1>{cinema.name}</h1>
            {cinema.address && <p>{cinema.address}</p>}
            <div className="detail-meta">
              <span>{cinema.screens_count} {cinema.screens_count === 1 ? 'screen' : 'screens'}</span>
              {cinema.formats.filter(format => format !== '2D').map(format => <span key={format}>{format}</span>)}
              <a className="map-chip" href={mapLink(cinema.latitude, cinema.longitude)} target="_blank" rel="noopener noreferrer">View on map ↗</a>
            </div>
          </section>
          <div className="section-heading show-heading">
            <div><span className="eyebrow">NOW SHOWING HERE</span><h2>Movies and showtimes</h2></div>
          </div>
          <DayTabs days={days} value={day} onChange={chooseDay} />
          {error && <ErrorState message={error} />}
          {showsLoading ? <LoadingState /> : films.length === 0 ? (
            <EmptyState>No shows at this cinema on this day.</EmptyState>
          ) : (
            <div className="cinema-list">
              {films.map(film => (
                <article className="cinema-row" key={film.movie_id}>
                  <div className="cinema-row-head">
                    <Link to={`/movies/${film.movie_id}`} className="cinema-name">{film.title}</Link>
                    <small>{film.shows.length} {film.shows.length === 1 ? 'show' : 'shows'}</small>
                  </div>
                  <div className="time-pills">
                    {film.shows.map(show => <ShowtimeButton show={show} compact key={show.id} />)}
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </Shell>
  )
}

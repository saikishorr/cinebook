import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCinemas } from '../api'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import Shell from '../components/Shell'
import { mapLink } from '../utils/format'
import { useDocumentTitle } from '../utils/hooks'

// Real Pune cinemas: names and locations are real; showtimes on CineBook are a demo.
export default function Cinemas() {
  const [cinemas, setCinemas] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [chain, setChain] = useState('')
  useDocumentTitle('Cinemas in Pune')

  const load = useCallback(() => {
    let active = true
    getCinemas()
      .then(data => { if (active) setCinemas(data) })
      .catch(requestError => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => load(), [load])

  const chains = useMemo(() => [...new Set(cinemas.map(cinema => cinema.chain))].sort(), [cinemas])
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return cinemas.filter(cinema => (!chain || cinema.chain === chain) &&
      (!needle || `${cinema.name} ${cinema.area} ${cinema.address || ''}`.toLowerCase().includes(needle)))
  }, [cinemas, query, chain])

  return (
    <Shell>
      <div className="section-heading">
        <div><span className="eyebrow">PUNE</span><h1 className="page-title">Cinemas<span className="accent">.</span></h1></div>
        <span className="muted">{visible.length} of {cinemas.length} cinemas</span>
      </div>
      {!loading && !error && cinemas.length > 0 && (
        <div className="movie-toolbar">
          <label className="search-field">
            <span aria-hidden="true">⌕</span>
            <input type="search" value={query} onChange={event => setQuery(event.target.value)}
                   placeholder="Search by cinema or area, e.g. Kothrud" aria-label="Search cinemas" />
          </label>
          <div className="chip-row" role="group" aria-label="Filter by chain">
            {['', ...chains].map(item => (
              <button type="button" key={item || 'all'} className={`chip ${chain === item ? 'active' : ''}`}
                      aria-pressed={chain === item} onClick={() => setChain(item)}>{item || 'All'}</button>
            ))}
          </div>
        </div>
      )}
      {loading ? <LoadingState /> : error ? <ErrorState message={error} onRetry={() => { setLoading(true); setError(''); load() }} /> :
        visible.length === 0 ? <EmptyState title="No matching cinemas">Try another area or chain.</EmptyState> : (
          <div className="cinema-grid">
            {visible.map(cinema => (
              <article className="cinema-card" key={cinema.id}>
                <span className="cinema-chain">{cinema.chain}</span>
                <h2><Link to={`/cinemas/${cinema.id}`}>{cinema.name}</Link></h2>
                <p className="cinema-area">{cinema.area}</p>
                {cinema.address && <p className="cinema-address">{cinema.address}</p>}
                <div className="cinema-card-foot">
                  <span>{cinema.screens_count} {cinema.screens_count === 1 ? 'screen' : 'screens'}</span>
                  <a href={mapLink(cinema.latitude, cinema.longitude)} target="_blank" rel="noopener noreferrer">Map ↗</a>
                  <Link className="card-cta" to={`/cinemas/${cinema.id}`}>Showtimes <b>→</b></Link>
                </div>
              </article>
            ))}
          </div>
        )}
    </Shell>
  )
}

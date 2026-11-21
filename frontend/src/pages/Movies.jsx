import { useCallback, useEffect, useMemo, useState } from 'react'
import { getMovies } from '../api'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import MovieCard from '../components/MovieCard'
import Shell from '../components/Shell'
import { useDocumentTitle } from '../utils/hooks'

const ALL = 'All'

export default function Movies() {
  const [movies, setMovies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [language, setLanguage] = useState(ALL)
  useDocumentTitle('Now Showing in Pune')

  const load = useCallback(() => {
    let active = true
    getMovies({ showing: true })
      .then(data => { if (active) setMovies(data) })
      .catch(requestError => { if (active) setError(requestError.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => load(), [load])

  function retry() {
    setLoading(true)
    setError('')
    load()
  }

  const languages = useMemo(() => [ALL, ...new Set(movies.map(movie => movie.language).filter(Boolean))], [movies])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return movies.filter(movie =>
      (language === ALL || movie.language === language) &&
      (!needle || `${movie.title} ${movie.description || ''}`.toLowerCase().includes(needle)))
  }, [movies, query, language])

  const filtering = query.trim() !== '' || language !== ALL

  return (
    <Shell>
      <section className="hero">
        <div>
          <span className="eyebrow"><i /> NOW PLAYING</span>
          <h1>Now Showing in Pune<span className="accent">.</span></h1>
          <p>Every language, at Pune's cinemas. Pick a film, a cinema and your seats.</p>
        </div>
        <div className="hero-side">
          <span>CURATED FOR YOUR NEXT NIGHT OUT</span>
          <strong>Stories worth<br />leaving home for.</strong>
        </div>
      </section>
      <div className="section-heading">
        <div><span className="eyebrow">THE BIG SCREEN</span><h2>In cinemas now</h2></div>
        <span className="muted">{filtering ? `${visible.length} of ${movies.length}` : movies.length} films</span>
      </div>

      {!loading && !error && movies.length > 0 && (
        <div className="movie-toolbar">
          <label className="search-field">
            <span aria-hidden="true">⌕</span>
            <input type="search" value={query} onChange={event => setQuery(event.target.value)}
                   placeholder="Search movies" aria-label="Search movies" />
          </label>
          {languages.length > 2 && (
            <div className="chip-row" role="group" aria-label="Filter by language">
              {languages.map(item => (
                <button type="button" key={item} className={`chip ${language === item ? 'active' : ''}`}
                        aria-pressed={language === item} onClick={() => setLanguage(item)}>{item}</button>
              ))}
            </div>
          )}
        </div>
      )}

      {loading ? <LoadingState /> : error ? <ErrorState message={error} onRetry={retry} /> : movies.length === 0 ? (
        <EmptyState title="No movies showing right now">Check back soon for the latest releases.</EmptyState>
      ) : visible.length === 0 ? (
        <EmptyState title="No matching movies">
          Try another search, or <button type="button" className="link-button" onClick={() => { setQuery(''); setLanguage(ALL) }}>clear the filters</button>.
        </EmptyState>
      ) : (
        <div className="movie-grid">{visible.map(movie => <MovieCard movie={movie} key={movie.id} />)}</div>
      )}
    </Shell>
  )
}

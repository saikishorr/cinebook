import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminAddMovie, adminExport, adminMovies, adminSearchTmdb, adminSetActive } from '../../api'
import ErrorState from '../../components/ErrorState'
import Poster from '../../components/Poster'
import Toast from '../../components/Toast'

const LANGUAGES = ['Marathi', 'Hindi', 'English', 'Telugu', 'Tamil', 'Malayalam', 'Kannada', 'Gujarati', 'Punjabi', 'Bengali', 'Japanese', 'Korean']
const TMDB_LANGUAGE = { mr: 'Marathi', hi: 'Hindi', en: 'English', te: 'Telugu', ta: 'Tamil', ml: 'Malayalam', kn: 'Kannada', gu: 'Gujarati', pa: 'Punjabi', bn: 'Bengali', ja: 'Japanese', ko: 'Korean' }

// Films: which titles are playing in Pune this week, and adding new releases.
export default function Films({ onSignOut }) {
  const [movies, setMovies] = useState(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState(null)
  const [filter, setFilter] = useState('')
  const [toast, setToast] = useState('')

  // Any 401 clears the stored session; send the admin back to the sign-in form.
  const handle = useCallback(requestError => {
    if (requestError.status === 401) onSignOut()
    else setToast(requestError.message)
  }, [onSignOut])

  useEffect(() => {
    let active = true
    adminMovies()
      .then(data => { if (active) setMovies(data) })
      .catch(requestError => {
        if (!active) return
        if (requestError.status === 401) onSignOut()
        else setError(requestError.message)
      })
    return () => { active = false }
  }, [onSignOut])

  useEffect(() => {
    if (!toast) return undefined
    const id = setTimeout(() => setToast(''), 4000)
    return () => clearTimeout(id)
  }, [toast])

  async function toggle(movie) {
    setBusyId(movie.id)
    try {
      const updated = await adminSetActive(movie.id, !movie.is_active)
      setMovies(current => current.map(item => (item.id === updated.id ? updated : item)))
      setToast(updated.is_active ? `${updated.title} is now showing in Pune (${updated.upcoming_shows} shows scheduled).`
        : `${updated.title} is hidden. Booked shows were kept.`)
    } catch (requestError) {
      handle(requestError)
    } finally {
      setBusyId(null)
    }
  }

  async function exportList() {
    try {
      const data = await adminExport()
      const blob = new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = Object.assign(document.createElement('a'), { href: url, download: 'pune_now_showing.json' })
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setToast('Saved pune_now_showing.json. Replace db/data/pune_now_showing.json with it to keep these choices.')
    } catch (requestError) {
      handle(requestError)
    }
  }

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return (movies || []).filter(movie => !needle || `${movie.title} ${movie.language}`.toLowerCase().includes(needle))
  }, [movies, filter])
  const activeCount = (movies || []).filter(movie => movie.is_active).length

  return (
    <div className="admin-section">
      <div className="section-heading admin-head">
        <div><span className="eyebrow">CATALOGUE</span><h1 className="admin-title">Films in Pune</h1></div>
        <div className="admin-actions">
          <button type="button" className="button print-button" onClick={exportList}>Export list</button>
        </div>
      </div>
      <p className="admin-note">Tick the films Pune cinemas are screening this week. Showtimes are created as soon as a film is ticked,
        and an unticked film loses its unbooked shows (booked shows are kept). Running <code>import-movies.ps1</code> replaces these
        choices with <code>db/data/pune_now_showing.json</code>, so export the list into that file to keep them.</p>

      <AddFilm onAdded={movie => { setMovies(current => [movie, ...(current || []).filter(item => item.id !== movie.id)]); setToast(`${movie.title} added and scheduled.`) }}
               onError={handle} />

      {error ? <ErrorState message={error} /> : !movies ? <p className="muted">Loading films…</p> : (
        <>
          <div className="admin-list-head">
            <strong>{activeCount} of {movies.length} films showing</strong>
            <label className="search-field admin-filter">
              <span aria-hidden="true">⌕</span>
              <input type="search" value={filter} onChange={event => setFilter(event.target.value)} placeholder="Filter films" aria-label="Filter films" />
            </label>
          </div>
          <ul className="admin-films">
            {visible.map(movie => (
              <li key={movie.id} className={movie.is_active ? 'on' : 'off'}>
                <Poster movie={movie} />
                <div className="admin-film-copy">
                  <strong>{movie.title}</strong>
                  <small>{[movie.language, movie.certificate, `${movie.duration_minutes} min`, movie.tmdb_id ? null : 'not on TMDB'].filter(Boolean).join(' · ')}</small>
                  <small>{movie.is_active ? `${movie.upcoming_shows} upcoming shows` : 'Not showing'}</small>
                </div>
                <label className="switch">
                  <input type="checkbox" checked={movie.is_active} disabled={busyId === movie.id} onChange={() => toggle(movie)}
                         aria-label={`${movie.title} is showing in Pune`} />
                  <span aria-hidden="true" />
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      <Toast message={toast} />
    </div>
  )
}

function AddFilm({ onAdded, onError }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [manual, setManual] = useState({ title: '', language: 'Marathi', certificate: 'UA' })
  const [adding, setAdding] = useState(false)

  async function search(event) {
    event.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    try {
      setResults(await adminSearchTmdb(query.trim()))
    } catch (requestError) {
      onError(requestError)
    } finally {
      setSearching(false)
    }
  }

  async function add(film) {
    setAdding(true)
    try {
      onAdded(await adminAddMovie(film))
      setResults(null)
      setQuery('')
      setManual(current => ({ ...current, title: '' }))
    } catch (requestError) {
      onError(requestError)
    } finally {
      setAdding(false)
    }
  }

  return (
    <section className="panel admin-add">
      <span className="eyebrow">ADD A NEW RELEASE</span>
      <form className="admin-search" onSubmit={search}>
        <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search TMDB, e.g. a new Marathi film" aria-label="Search TMDB" />
        <button className="button primary" disabled={searching || query.trim().length < 2}>{searching ? 'Searching…' : 'Search'}</button>
      </form>
      {results && (results.length === 0 ? <p className="muted">No TMDB results. Add it by hand below.</p> : (
        <ul className="tmdb-results">
          {results.map(result => {
            const language = TMDB_LANGUAGE[result.original_language] || result.original_language.toUpperCase()
            return (
              <li key={result.tmdb_id}>
                {result.poster_url ? <img src={result.poster_url} alt="" loading="lazy" /> : <span className="tmdb-noposter">✦</span>}
                <div><strong>{result.title}</strong><small>{language} · {result.release_date || 'date unknown'}</small></div>
                <button type="button" className="button print-button" disabled={adding}
                        onClick={() => add({ tmdb_id: result.tmdb_id, title: result.title, language, certificate: 'UA' })}>Add</button>
              </li>
            )
          })}
        </ul>
      ))}
      <form className="admin-manual" onSubmit={event => { event.preventDefault(); if (manual.title.trim()) add({ tmdb_id: null, ...manual, title: manual.title.trim() }) }}>
        <span className="muted">Not on TMDB yet?</span>
        <input value={manual.title} onChange={event => setManual({ ...manual, title: event.target.value })} placeholder="Film title" aria-label="Film title" />
        <select value={manual.language} onChange={event => setManual({ ...manual, language: event.target.value })} aria-label="Language">
          {LANGUAGES.map(language => <option key={language}>{language}</option>)}
        </select>
        <select value={manual.certificate} onChange={event => setManual({ ...manual, certificate: event.target.value })} aria-label="Certificate">
          {['U', 'UA', 'A'].map(value => <option key={value}>{value}</option>)}
        </select>
        <button className="button print-button" disabled={adding || !manual.title.trim()}>Add by hand</button>
      </form>
    </section>
  )
}

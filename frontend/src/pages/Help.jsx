import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getHelp } from '../api'
import ErrorState from '../components/ErrorState'
import Shell from '../components/Shell'
import { useDocumentTitle } from '../utils/hooks'

// Phase 3: the cinema's published policies and facilities.
// The chat assistant answers from exactly this content, so the page and the assistant always agree.
export default function Help() {
  useDocumentTitle('Help & info')
  const [help, setHelp] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getHelp()
      .then(data => { if (active) setHelp(data) })
      .catch(requestError => { if (active) setError(requestError.message) })
    return () => { active = false }
  }, [])

  if (error) return <Shell><ErrorState message={error} /></Shell>
  if (!help) return <Shell><div className="state-panel pending-panel"><span className="pending-spinner" aria-hidden="true" /><h1>Loading help…</h1></div></Shell>

  return (
    <Shell>
      <div className="help-page">
        <Link className="back-link" to="/">← <span>Back to movies</span></Link>
        <span className="eyebrow">CINEBOOK</span>
        <h1>{help.title}<span className="accent">.</span></h1>
        <p className="help-notice">{help.notice}</p>
        <nav className="help-nav" aria-label="Help sections">
          {help.sections.map(section => <a key={section.id} href={`#${section.id}`}>{section.title}</a>)}
        </nav>
        {help.sections.map(section => (
          <section className="help-section panel" id={section.id} key={section.id}>
            <h2>{section.title}</h2>
            {section.items.map(item => (
              <details className="help-item" key={item.q}>
                <summary>{item.q}</summary>
                <p>{item.a}</p>
              </details>
            ))}
          </section>
        ))}
        <p className="help-updated">Last updated {help.updated}</p>
      </div>
    </Shell>
  )
}

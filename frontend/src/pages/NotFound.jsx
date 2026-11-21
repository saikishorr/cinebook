import { Link } from 'react-router-dom'
import Shell from '../components/Shell'
import { useDocumentTitle } from '../utils/hooks'

export default function NotFound() {
  useDocumentTitle('Page not found')
  return (
    <Shell>
      <div className="state-panel">
        <span className="state-icon">✦</span>
        <span className="eyebrow">SCENE NOT FOUND</span>
        <h1>Page not found</h1>
        <p>Looks like this scene isn't in our movie.</p>
        <Link className="button primary" to="/">Back to CineBook</Link>
      </div>
    </Shell>
  )
}

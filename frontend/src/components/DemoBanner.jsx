import { Link } from 'react-router-dom'

// Shown on every page: the cinemas are real, CineBook is not connected to them.
export default function DemoBanner() {
  return (
    <div className="demo-banner" role="note">
      <b>Demo site.</b> Cinemas are real Pune venues, but showtimes, prices and seats are simulated.
      CineBook is not connected to these cinemas, and its tickets are not valid for entry. <Link to="/help">Learn more</Link>
    </div>
  )
}

import DemoBanner from './DemoBanner'
import Header from './Header'

export default function Shell({ children }) {
  return (
    <>
      <Header />
      <DemoBanner />
      <main className="page-wrap">{children}</main>
      <footer className="footer">
        A better seat for every story <span>·</span> CineBook
        <small className="tmdb-credit">Movie data and images from TMDB. This product uses the TMDB API but is not endorsed or certified by TMDB. Cinema locations © OpenStreetMap contributors. CineBook is not affiliated with any cinema.</small>
      </footer>
    </>
  )
}

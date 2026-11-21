import { Link } from 'react-router-dom'
import Poster from './Poster'

export default function MovieCard({ movie }) {
  return (
    <Link className="movie-card" to={`/movies/${movie.id}`}>
      <Poster movie={movie} />
      <div className="movie-info">
        <div className="movie-meta">
          <span>{movie.language || 'Feature film'}</span>
          {movie.certificate && <span className="cert">{movie.certificate}</span>}
          {movie.genres?.length > 0 && <span className="card-genres">{movie.genres.slice(0, 2).join(' · ')}</span>}
        </div>
        <h3>{movie.title}</h3>
        <p>{movie.description || 'A story made for the big screen.'}</p>
        <div className="movie-foot">
          {movie.duration_minutes && <span>{movie.duration_minutes} min</span>}
          <span className="card-cta">{movie.cinemas_count ? `${movie.cinemas_count} cinemas` : 'View showtimes'} <b>↗</b></span>
        </div>
      </div>
    </Link>
  )
}

import { useState } from 'react'

export default function Poster({ movie, large = false }) {
  const [imageFailed, setImageFailed] = useState(false)
  const hue = (String(movie?.title || 'Cinema').length * 43) % 360

  return (
    <div
      className={`poster ${large ? 'poster-large' : ''}`}
      style={{ '--poster-hue': `${hue}deg` }}
    >
      {movie?.poster_url && !imageFailed ? (
        <img
          src={movie.poster_url}
          alt={`${movie.title} poster`}
          onError={() => setImageFailed(true)}
        />
      ) : (
        <div className="poster-art">
          <span className="poster-kicker">CINEBOOK ORIGINAL</span>
          <strong>{movie?.title || 'Now Showing'}</strong>
          <i>✦</i>
        </div>
      )}
      <div className="poster-shade" />
    </div>
  )
}

export default function LoadingState() {
  return (
    <div className="movie-grid" aria-label="Loading">
      {[1, 2, 3, 4].map(item => (
        <div className="skeleton-card" key={item}>
          <div className="shimmer poster-skeleton" />
          <div className="shimmer line" />
          <div className="shimmer line short" />
        </div>
      ))}
    </div>
  )
}

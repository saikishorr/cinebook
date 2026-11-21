export default function ErrorState({ message, onRetry }) {
  return (
    <section className="notice error" role="alert">
      <b>We couldn't load this page</b>
      <span>{message || 'Please check that the CineBook backend is running.'}</span>
      {onRetry && <button type="button" className="button retry-button" onClick={onRetry}>Try again</button>}
    </section>
  )
}

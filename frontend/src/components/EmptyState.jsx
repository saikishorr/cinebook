export default function EmptyState({ title = 'Nothing to show yet', children }) {
  return (
    <div className="empty">
      <span className="empty-icon">✦</span>
      <h2>{title}</h2>
      <p>{children}</p>
    </div>
  )
}

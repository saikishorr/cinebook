import { formatCountdown } from '../utils/format'

export default function Countdown({ seconds, compact = false }) {
  const urgent = seconds < 60
  const formatted = formatCountdown(seconds)

  return compact ? (
    <div className={`countdown-box ${urgent ? 'urgent' : ''}`}>
      <span>◷</span>
      <div><small>Hold expires in</small><b>{formatted}</b></div>
    </div>
  ) : (
    <div className={`countdown ${urgent ? 'urgent' : ''}`} role="timer" aria-live={urgent ? 'polite' : 'off'}>
      <span>HOLD EXPIRES IN</span>
      <strong>{formatted}</strong>
    </div>
  )
}

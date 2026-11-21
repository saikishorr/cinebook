import { useEffect, useState } from 'react'

/** Sets the browser tab title, e.g. "Pick your seats · CineBook". */
export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · CineBook` : 'CineBook – Movie Tickets'
  }, [title])
}

/**
 * Seconds left until an absolute time (ISO string or Date).
 * Counting from the deadline, not by subtracting one per tick, keeps it right when a
 * background tab throttles timers or the computer sleeps.
 */
export function useSecondsUntil(deadline) {
  const target = deadline ? new Date(deadline).getTime() : null
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!target) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [target])

  // `now` can be up to a second old, which errs on the side of time left: a freshly loaded
  // deadline never reads as expired. null = no deadline yet.
  return target === null ? null : Math.max(0, Math.round((target - now) / 1000))
}

/** Runs `callback` every `ms` while the tab is visible, and once more when it becomes visible again. */
export function useVisibleInterval(callback, ms) {
  useEffect(() => {
    let id = null
    const start = () => { if (id === null) id = setInterval(callback, ms) }
    const stop = () => { if (id !== null) { clearInterval(id); id = null } }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') { callback(); start() } else stop()
    }
    if (document.visibilityState === 'visible') start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => { stop(); document.removeEventListener('visibilitychange', onVisibility) }
  }, [callback, ms])
}

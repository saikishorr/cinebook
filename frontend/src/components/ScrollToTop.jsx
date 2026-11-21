import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

// BrowserRouter keeps the old scroll position between pages; start every new page at the top.
// In-page anchors (#section on the Help page) are left to the browser.
export default function ScrollToTop() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0)
  }, [pathname, hash])
  return null
}

import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Header() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)
  const navigate = useNavigate()
  const location = useLocation()
  const here = `${location.pathname}${location.search}`

  // Close the account menu on an outside click or Escape.
  useEffect(() => {
    if (!open) return undefined
    const onClick = event => { if (!menuRef.current?.contains(event.target)) setOpen(false) }
    const onKey = event => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onClick); document.removeEventListener('keydown', onKey) }
  }, [open])

  async function handleSignOut() {
    setOpen(false)
    await signOut()
    navigate('/')
  }

  return (
    <header className="site-header">
      <Link className="brand" to="/">
        <span className="brand-mark">✦</span>
        CineBook
      </Link>
      <nav className="header-nav" aria-label="Main">
        <span className="header-note">Pune</span>
        <NavLink className="header-link" to="/" end>Movies</NavLink>
        <NavLink className="header-link" to="/cinemas">Cinemas</NavLink>
        <NavLink className="header-link hide-small" to="/help">Help</NavLink>
        {user ? (
          <div className="account-menu" ref={menuRef}>
            <button type="button" className="account-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(value => !value)}>
              <span className="avatar" aria-hidden="true">{user.full_name.trim()[0]?.toUpperCase()}</span>
              <span className="hide-small">{user.full_name.split(' ')[0]}</span>
            </button>
            {open && (
              <div className="account-dropdown" role="menu">
                <div className="account-who"><strong>{user.full_name}</strong><small>{user.email}</small></div>
                <Link role="menuitem" to="/my-bookings" onClick={() => setOpen(false)}>My bookings</Link>
                <Link role="menuitem" to="/booking" onClick={() => setOpen(false)}>Find a booking</Link>
                <Link role="menuitem" to="/demo-phone" onClick={() => setOpen(false)}>Demo Phone</Link>
                <button type="button" role="menuitem" onClick={handleSignOut}>Sign out</button>
              </div>
            )}
          </div>
        ) : (
          <Link className="button primary sign-in-button" to={`/login?next=${encodeURIComponent(here)}`}>Sign in</Link>
        )}
      </nav>
    </header>
  )
}

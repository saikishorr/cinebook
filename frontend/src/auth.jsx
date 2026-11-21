import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getMe, registerAccount, saveUserSession, signInAccount, signOutAccount, userSession } from './api'

// The signed-in customer, shared by every page. Booking needs a signed-in account (like BookMyShow);
// browsing movies, cinemas and showtimes does not.
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(userSession)

  const remember = useCallback(next => {
    saveUserSession(next)
    setSession(next)
  }, [])

  // Re-check a stored session once on start-up: it may have expired, been signed out elsewhere, or blocked.
  useEffect(() => {
    if (!userSession()) return undefined
    let active = true
    getMe()
      .then(user => { if (active) remember({ ...userSession(), user }) })
      .catch(error => { if (active && (error.status === 401 || error.status === 403)) remember(null) })
    return () => { active = false }
  }, [remember])

  const value = useMemo(() => ({
    user: session?.user || null,
    signIn: async (email, password) => remember(await signInAccount(email, password)),
    register: async details => remember(await registerAccount(details)),
    signOut: async () => {
      try { await signOutAccount() } catch { /* already gone on the server */ }
      remember(null)
    },
    updateUser: user => remember({ ...userSession(), user }),
    // Call when the API answers 401: the session ended on the server.
    expired: () => remember(null),
  }), [session, remember])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react/only-export-components -- the hook belongs with its provider
export function useAuth() {
  return useContext(AuthContext)
}

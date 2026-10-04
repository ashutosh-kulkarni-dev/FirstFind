// The single source of truth for auth state. React state (not module globals) so
// every consumer re-renders the instant login/logout happens — fixing the stale
// navbar bug. api.js stays a thin transport that this context drives.
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { AUTH_UNAUTHORIZED_EVENT, api, getToken, getUser, resetSession, setAuth } from '../api'
import { getSaved } from '../lib/saved'
import { resumePendingAction } from './pendingAction'

const AuthCtx = createContext({
  user: null, loading: true,
  login: () => {}, logout: () => {},
})

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getUser())
  const [loading, setLoading] = useState(!!getToken())

  // On load, if we have a stored token, validate + hydrate it against the server.
  // A bad/expired token is cleared so we never render a "logged-in" UI on a dead
  // session.
  useEffect(() => {
    if (!getToken()) { setLoading(false); return }
    let cancelled = false
    api.me()
      .then(res => {
        if (cancelled) return
        setAuth(res.token, res)   // refresh token (sliding expiry) + latest profile
        setUser(res)
      })
      .catch(() => { if (!cancelled) { setAuth(null, null); setUser(null) } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const login = useCallback((token, userObj) => {
    setAuth(token, userObj)
    setUser(userObj)
    // Migrate guest-hearted stores to the server so the recommender can use them
    // immediately. Fire-and-forget: failures are silent (the localStorage copy
    // stays intact so nothing is lost). Each save is idempotent on the backend.
    const guestSaved = getSaved()
    if (guestSaved.length > 0) {
      Promise.allSettled(guestSaved.map(id => api.saveStore(id)))
    }
    // Replay whatever privileged action the guest was mid-way through.
    resumePendingAction()
  }, [])

  const logout = useCallback(() => {
    setAuth(null, null)
    setUser(null)
    // Start a clean chat session so a different user on this tab never inherits
    // the previous user's conversation state on the backend.
    resetSession()
  }, [])

  // A 401 on any authed request means the token died server-side — log out cleanly.
  useEffect(() => {
    const onUnauthorized = () => logout()
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
  }, [logout])

  return (
    <AuthCtx.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthCtx.Provider>
  )
}

export const useAuth = () => useContext(AuthCtx)

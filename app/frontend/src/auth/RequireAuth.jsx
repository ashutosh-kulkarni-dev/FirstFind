// Gating primitives, built on AuthContext + pendingAction.
//   <RequireAuth> — guards a whole privileged view for guests.
//   useRequireAuth() — guards a single action (save, review, …): runs it if
//                      logged in, else queues it and sends the guest to log in.
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { setPendingAction } from './pendingAction'

// Wrap a route/section that only makes sense when logged in.
export function RequireAuth({ children, message = 'Log in to use this feature.' }) {
  const { user, loading } = useAuth()
  const { pathname } = useLocation()
  if (loading) return null
  if (user) return children
  return (
    <div style={{ display: 'grid', placeItems: 'center', minHeight: 'calc(100vh - 60px)', padding: 24 }}>
      <div className="card" style={{ padding: 28, textAlign: 'center', maxWidth: 380 }}>
        <p className="muted" style={{ fontSize: 14, marginBottom: 16 }}>{message}</p>
        <Link to={`/auth?next=${encodeURIComponent(pathname)}`} className="btn btn-primary">Log in</Link>
      </div>
    </div>
  )
}

// Returns guard(action, { pending }) — call it from a privileged button's onClick.
//   action:  () => void   run immediately when already authenticated.
//   pending: { type, payload }  optional descriptor replayed after login (its
//            handler must be registered via registerActionHandler in that feature).
export function useRequireAuth() {
  const { user } = useAuth()
  const nav = useNavigate()
  const { pathname } = useLocation()
  return (action, { pending } = {}) => {
    if (user) { action?.(); return true }
    if (pending) setPendingAction(pending)
    nav(`/auth?next=${encodeURIComponent(pathname)}`)
    return false
  }
}

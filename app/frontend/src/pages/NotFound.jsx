import { Link } from 'react-router-dom'

// Catch-all for unknown routes so a bad URL never renders a blank page.
export default function NotFound() {
  return (
    <div style={{ flex: 1, display: 'grid', placeItems: 'center', padding: 24, minHeight: 'calc(100vh - 60px)' }}>
      <div className="card fade-up" style={{ padding: 32, textAlign: 'center', maxWidth: 400 }}>
        <div className="anton" style={{ fontSize: 64, color: 'var(--ink)', lineHeight: 1 }}>404</div>
        <p className="muted" style={{ fontSize: 14, marginTop: 10, marginBottom: 20 }}>
          We couldn't find that page. It may have moved, or the link is wrong.
        </p>
        <Link to="/" className="btn btn-primary">Back to home</Link>
      </div>
    </div>
  )
}

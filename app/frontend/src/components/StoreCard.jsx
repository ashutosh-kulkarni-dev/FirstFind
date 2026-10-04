import { Link } from 'react-router-dom'
import ScorePill from './ScorePill'

// Compact store preview card (used on Landing, Chat results, similar lists).
export default function StoreCard({ store, match }) {
  // `categories` is an array from the API but a comma-string in some contexts —
  // handle both so `.split` is never called on an array (which throws and blanks the page).
  const cats = Array.isArray(store.categories)
    ? store.categories
    : String(store.categories || '').split(',').map(s => s.trim()).filter(Boolean)
  const open = store.is_open_now
  return (
    <Link to={`/store/${store.id}`} className="card card-link" style={{ display: 'block', padding: 13, textDecoration: 'none' }}>
      <div className="anton" style={{ fontSize: 15, color: 'var(--ink)' }}>{(store.name || '').toUpperCase()}</div>
      <div style={{ marginTop: 2, color: 'var(--muted)', fontSize: 11.5 }}>
        {store.area}{cats[0] ? ` · ${cats[0]}` : ''}
      </div>
      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
        <ScorePill score={store.experience_score} />
        {store.price_min != null && (
          <span style={{ color: 'var(--muted)', fontSize: 11, fontWeight: 600 }}>
            {'₹'.repeat(Math.max(1, Math.min(3, Math.ceil((store.price_max || 500) / 800))))}
          </span>
        )}
        {match != null ? (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--brand-blue-2)', fontWeight: 700 }}>{match}% match</span>
        ) : open != null ? (
          <span style={{ marginLeft: 'auto', fontSize: 10.5, fontWeight: 700, color: open ? 'var(--sent-pos)' : 'var(--muted-2)' }}>
            {open ? 'Open' : 'Closed'}
          </span>
        ) : null}
      </div>
    </Link>
  )
}

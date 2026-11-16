import { Link } from 'react-router-dom'

// Bottom of the sidebar: the visitor's saved lists, or a prompt to log in.
// `lists` is null while loading.
export default function MyListsPanel({ user, lists }) {
  return (
    <div className="explore-lists">
      <div className="section-eyebrow explore-lists-title">Your lists</div>
      {!user ? (
        <div className="explore-lists-note">
          <Link to="/auth?next=%2Fexplore">Log in</Link> or{' '}
          <Link to="/auth?mode=register&next=%2Fexplore">create an account</Link>
          {' '}to save lists and come back later.
        </div>
      ) : lists === null ? (
        <span className="muted explore-lists-loading">Loading…</span>
      ) : lists.length === 0 ? (
        <div className="explore-lists-note">
          No lists yet. Double-click the map to cluster stores, then save as a list.
        </div>
      ) : (
        <div className="explore-lists-items">
          {lists.slice(0, 4).map(l => (
            <Link key={l.id} to="/lists" className="explore-list-row">
              <span className="explore-list-name">{l.name}</span>
              <span className="explore-list-count">{l.store_count} store{l.store_count !== 1 ? 's' : ''}</span>
            </Link>
          ))}
          {lists.length > 4 && (
            <Link to="/lists" className="explore-lists-more">View all {lists.length} lists →</Link>
          )}
        </div>
      )}
    </div>
  )
}

// One review with Hide/Unhide and Delete (confirmed). Shared by the Reviews tab
// and the store drawer.
import { useState } from 'react'
import { api } from '../../api'
import ConfirmDialog from './ConfirmDialog'

export default function ReviewRow({ review: r, showStore = true, onOpenStore, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [error, setError] = useState('')

  const run = async (fn, msg) => {
    setBusy(true); setError('')
    try { await fn(); setConfirm(false); onChanged(msg) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className={`admin-review ${r.is_hidden ? 'is-hidden' : ''}`}>
      <div className="admin-review-meta">
        <span className="admin-stars" aria-label={`${r.rating} stars`}>{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>
        <span>{r.author || 'Anonymous'}</span>
        <span className="muted">· {r.source}</span>
        {r.sentiment && <span className="muted">· {r.sentiment}</span>}
        {r.is_hidden && <span className="admin-flag">Hidden</span>}
        {showStore && (
          <button className="link-btn" onClick={() => onOpenStore?.(r.store_id)}>{r.store_name}</button>
        )}
      </div>
      <p className="admin-review-text">{r.text || <span className="muted">(no text)</span>}</p>
      {error && <p className="admin-error">{error}</p>}
      <div className="admin-row-actions">
        <button className="pill-btn" disabled={busy}
          onClick={() => run(() => api.adminSetReviewHidden(r.id, !r.is_hidden),
            r.is_hidden ? 'Review is visible again' : 'Review hidden')}>
          {r.is_hidden ? 'Unhide' : 'Hide'}
        </button>
        <button className="pill-btn pill-danger" disabled={busy} onClick={() => setConfirm(true)}>Delete</button>
      </div>
      {confirm && (
        <ConfirmDialog title="Delete this review?" confirmLabel="Delete permanently" busy={busy}
          onConfirm={() => run(() => api.adminDeleteReview(r.id), 'Review deleted')}
          onCancel={() => setConfirm(false)}>
          <p>The review is removed for good and the store's score is recalculated. Hiding it keeps a copy instead.</p>
        </ConfirmDialog>
      )}
    </div>
  )
}

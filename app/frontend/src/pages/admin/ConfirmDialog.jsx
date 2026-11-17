// Modal confirmation for permanent actions. Escape or the backdrop cancels.
import { useEffect } from 'react'

export default function ConfirmDialog({ title, children, confirmLabel = 'Delete', busy, onConfirm, onCancel }) {
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  return (
    <div className="admin-modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onCancel() }}>
      <div className="card admin-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title" className="admin-modal-title">{title}</h2>
        <div className="admin-modal-body">{children}</div>
        <div className="admin-modal-actions">
          <button className="btn" onClick={onCancel} disabled={busy} autoFocus>Cancel</button>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

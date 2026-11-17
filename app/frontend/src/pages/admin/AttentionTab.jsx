import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'

const REASONS = [
  { code: '', label: 'All' },
  { code: 'not_on_google', label: 'Not on Google' },
  { code: 'no_pin', label: 'No pin' },
  { code: 'placeholder_name', label: 'Placeholder name' },
  { code: 'duplicate', label: 'Possible duplicate' },
]

export default function AttentionTab({ version, onOpen }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')

  useEffect(() => {
    let cancelled = false
    api.adminAttention()
      .then(r => { if (!cancelled) setData(r) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [version])

  const items = useMemo(() => (data?.items || [])
    .filter(it => !reason || it.reasons.some(r => r.code === reason)), [data, reason])

  return (
    <section>
      <div className="admin-toolbar">
        <div className="admin-seg" role="group" aria-label="Filter by reason">
          {REASONS.map(r => (
            <button key={r.code} className={reason === r.code ? 'active' : ''} onClick={() => setReason(r.code)}>
              {r.label}{data && r.code ? ` (${data.by_reason[r.code] || 0})` : ''}
            </button>
          ))}
        </div>
      </div>
      <p className="muted admin-hint">
        Stores that probably need fixing. Hidden stores are included so you can decide whether to restore them.
      </p>
      {error && <p className="admin-error">{error}</p>}
      {!data && !error && <p className="muted">Checking stores…</p>}
      {data && (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>ID</th><th>Name</th><th>Area</th><th>Why</th><th>Status</th><th /></tr></thead>
            <tbody>
              {items.map(({ store: s, reasons }) => (
                <tr key={s.id} className={s.is_active ? '' : 'is-hidden'}>
                  <td className="mono">{s.id}</td>
                  <td><button className="link-btn" onClick={() => onOpen(s.id)}>{s.name}</button></td>
                  <td>{s.area}</td>
                  <td>{reasons.map(r => <span key={r.code} className="admin-flag">{r.label}</span>)}</td>
                  <td>{s.is_active ? 'Visible' : 'Hidden'}</td>
                  <td><button className="pill-btn" onClick={() => onOpen(s.id)}>Fix</button></td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={6} className="muted">Nothing here.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

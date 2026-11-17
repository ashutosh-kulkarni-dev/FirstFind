import { useEffect, useState } from 'react'
import { api } from '../../api'

const PAGE = 50

const fmt = v => (v === null || v === undefined || v === '' ? '—' : String(v))

function Changes({ entry }) {
  const c = entry.changes
  if (!c) return null
  if (entry.action === 'update') {
    return (
      <ul className="admin-diff">
        {Object.entries(c).map(([field, [before, after]]) => (
          <li key={field}><b>{field}</b>: <s className="muted">{fmt(before)}</s> → {fmt(after)}</li>
        ))}
      </ul>
    )
  }
  if (entry.entity === 'review' && c.text) return <div className="muted admin-diff">“{c.text}”</div>
  if (c.name) return <div className="muted admin-diff">{c.name}{c.area ? ` · ${c.area}` : ''}</div>
  return null
}

export default function ChangeLog({ version, onOpen }) {
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.adminAudit({ limit: PAGE, offset: page * PAGE })
      .then(r => { if (!cancelled) setData(r) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [page, version])

  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE)) : 1

  return (
    <section>
      {error && <p className="admin-error">{error}</p>}
      {!data && !error && <p className="muted">Loading…</p>}
      {data && data.entries.length === 0 && <p className="muted">No changes yet.</p>}
      {data && data.entries.length > 0 && (
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>When</th><th>Who</th><th>What</th><th>Item</th><th>Details</th></tr></thead>
            <tbody>
              {data.entries.map(e => (
                <tr key={e.id}>
                  <td className="nowrap">{new Date(e.created_at + 'Z').toLocaleString()}</td>
                  <td>{e.user_email}</td>
                  <td><span className={`admin-action a-${e.action}`}>{e.action}</span> {e.entity}</td>
                  <td className="mono">
                    {e.entity === 'store' && e.action !== 'delete'
                      ? <button className="link-btn" onClick={() => onOpen(e.entity_id)}>{e.entity_id}</button>
                      : e.entity === 'review' ? `#${e.entity_id}` : e.entity_id}
                  </td>
                  <td><Changes entry={e} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pages > 1 && (
        <div className="admin-pager">
          <button className="pill-btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Newer</button>
          <span className="muted">Page {page + 1} of {pages}</span>
          <button className="pill-btn" disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)}>Older →</button>
        </div>
      )}
    </section>
  )
}

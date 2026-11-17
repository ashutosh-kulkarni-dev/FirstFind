import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import ReviewRow from './ReviewRow'

const PAGE = 50

export default function ReviewsTab({ version, onChanged }) {
  const [, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')      // debounced copy of q
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const t = setTimeout(() => { setQuery(q); setPage(0) }, 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    let cancelled = false
    api.adminReviews({ q: query, status, limit: PAGE, offset: page * PAGE })
      .then(r => { if (!cancelled) { setData(r); setError('') } })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [query, status, page, version])

  const openStore = id => setParams(prev => { const n = new URLSearchParams(prev); n.set('store', id); return n })
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE)) : 1

  return (
    <section>
      <div className="admin-toolbar">
        <input className="input" style={{ maxWidth: 320 }} placeholder="Search review text"
          value={q} onChange={e => setQ(e.target.value)} aria-label="Search reviews" />
        <div className="admin-seg" role="group" aria-label="Filter by visibility">
          {['all', 'visible', 'hidden'].map(s => (
            <button key={s} className={status === s ? 'active' : ''}
              onClick={() => { setStatus(s); setPage(0) }}>{s[0].toUpperCase() + s.slice(1)}</button>
          ))}
        </div>
        {data && <span className="muted" style={{ fontSize: 12 }}>{data.count} reviews</span>}
      </div>
      {error && <p className="admin-error">{error}</p>}
      {!data && !error && <p className="muted">Loading reviews…</p>}
      {data?.reviews.map(r => (
        <ReviewRow key={r.id} review={r} onOpenStore={openStore} onChanged={onChanged} />
      ))}
      {data && data.reviews.length === 0 && <p className="muted">No reviews match.</p>}
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

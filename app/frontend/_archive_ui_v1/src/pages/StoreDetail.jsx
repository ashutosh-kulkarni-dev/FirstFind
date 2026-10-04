import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import StoreCard from '../components/StoreCard'
import { api, getUser } from '../api'

export default function StoreDetail() {
  const { id } = useParams()
  const [store, setStore] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [form, setForm] = useState({ rating: 5, text: '' })
  const [submitting, setSubmitting] = useState(false)
  const user = getUser()

  const load = () => api.store(id).then(setStore).catch(e => setError(e.message))
  useEffect(() => { load() }, [id])

  if (error) return <div className="detail container"><p className="err">{error}</p></div>
  if (!store) return <div className="detail container"><span className="spin" /></div>

  const ss = store.sentiment_summary || { positive: 0, neutral: 0, negative: 0, total: 0 }
  const visible = store.reviews

  async function save() {
    try { await api.saveStore(store.id); setSaved(true) } catch (e) { alert(e.message) }
  }
  async function submitReview() {
    if (!form.text.trim()) return
    setSubmitting(true)
    try {
      await api.addReview(store.id, Number(form.rating), form.text)
      setForm({ rating: 5, text: '' })
      await load()
      // Sentiment is scored asynchronously (a few secs) via the HF API, so refetch
      // shortly after to pick up the new review's sentiment + updated meter.
      setTimeout(load, 3000)
      setTimeout(load, 7000)
    } catch (e) { alert(e.message) } finally { setSubmitting(false) }
  }

  return (
    <div className="detail container">
      <div className="detail-head">
        <div>
          <h1>{store.name}</h1>
          <div className="meta-row" style={{ fontSize: 15 }}>
            <span>📍 {store.area}</span>
            {store.open_time && <span>🕐 {store.open_time}–{store.close_time || '?'}</span>}
            {store.closed_days?.length > 0 && <span>Closed {store.closed_days.join(', ')}</span>}
            {store.price_min && <span>₹{store.price_min}–{store.price_max}</span>}
            {store.phone && <span>📞 {store.phone}</span>}
            {store.instagram && <span>📸 {store.instagram}</span>}
          </div>
          {store.categories?.length > 0 && (
            <div className="tags">
              {store.categories.map(c => <span key={c} className="tag">{c}</span>)}
            </div>
          )}
          {store.notes && <p style={{ color: 'var(--text-dim)', marginTop: 12, fontSize: 14 }}>{store.notes}</p>}
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div className={`score-ring`}>
            <span className="v">{store.experience_score?.toFixed(1) ?? '—'}</span>
            <span className="l">AI SCORE</span>
          </div>
          {user && (
            <button className="btn" onClick={save} disabled={saved}>
              {saved ? '✓ Saved' : '♡ Save'}
            </button>
          )}
        </div>
      </div>

      <div className="detail-grid">
        <div>
          <h2 style={{ fontSize: 24, marginBottom: 4 }}>Community reviews</h2>
          <p style={{ color: 'var(--text-dim)', fontSize: 13 }}>
            {ss.total} reviews · sentiment: {ss.positive} positive / {ss.neutral} neutral / {ss.negative} negative
          </p>
          {ss.total > 0 && (
            <div className="sentiment-bar">
              <div className="pos" style={{ flex: ss.positive || 0.01 }} />
              <div className="neu" style={{ flex: ss.neutral || 0.01 }} />
              <div className="neg" style={{ flex: ss.negative || 0.01 }} />
            </div>
          )}

          {visible.map(r => (
            <div key={r.id} className="review">
              <div className="rhead">
                <span className="name">{r.user_name}</span>
                <span className="stars">{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</span>
                {r.sentiment && <span className={`sent-badge sent-${r.sentiment}`}>{r.sentiment}</span>}
                <span className="date">{r.created_at}</span>
              </div>
              <p>{r.text}</p>
            </div>
          ))}

          <div style={{ marginTop: 28 }}>
            <h3 style={{ marginBottom: 12 }}>Write a review</h3>
            {user ? (
              <>
                <div className="field">
                  <label>Rating</label>
                  <select value={form.rating} onChange={e => setForm(f => ({ ...f, rating: e.target.value }))}
                          style={{ padding: '10px 14px', borderRadius: 10, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text)' }}>
                    {[5, 4, 3, 2, 1].map(n => <option key={n} value={n}>{'★'.repeat(n)}</option>)}
                  </select>
                </div>
                <div className="field">
                  <textarea rows={3} placeholder="How was your haul?"
                            value={form.text} onChange={e => setForm(f => ({ ...f, text: e.target.value }))}
                            style={{ width: '100%', padding: 14, borderRadius: 10, background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text)', resize: 'vertical' }} />
                </div>
                <button className="btn btn-primary" onClick={submitReview} disabled={submitting}>
                  {submitting ? <span className="spin" /> : 'Post review'}
                </button>
              </>
            ) : (
              <p style={{ color: 'var(--text-dim)', fontSize: 14 }}>Log in to post a review.</p>
            )}
          </div>
        </div>

        <div>
          {store.similar.length > 0 && (
            <>
              <h3 style={{ marginBottom: 14 }}>Shoppers also liked</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {store.similar.map(s => <StoreCard key={s.id} store={s} compact />)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

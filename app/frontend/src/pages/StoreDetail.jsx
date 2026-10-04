import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useRequireAuth } from '../auth/RequireAuth'
import { registerActionHandler, resumePendingAction } from '../auth/pendingAction'
import ScoreRing from '../components/ScoreRing'
import StoreCard from '../components/StoreCard'
import { previewSentiment, isAnomalous } from '../lib/sentiment'
import { isSaved, toggleSaved } from '../lib/saved'

function sentBadge(s) {
  if (s === 'positive')  return { bg: '#dcfce7', ink: '#16a34a', label: 'POSITIVE' }
  if (s === 'negative')  return { bg: '#ffe4e6', ink: '#e11d48', label: 'NEGATIVE' }
  return { bg: 'var(--line-2)', ink: 'var(--sent-neutral)', label: 'NEUTRAL' }
}

export default function StoreDetail() {
  const { id } = useParams()
  const [store, setStore] = useState(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [rating, setRating] = useState(0)
  const [draft, setDraft] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [pendingReview, setPendingReview] = useState(null)
  const { user } = useAuth()
  const guard = useRequireAuth()
  const reloadTimers = useRef([])

  const load = () => api.store(id).then(d => { setStore(d); setSaved(isSaved(d.id)) }).catch(e => setError(e.message))
  useEffect(() => { load() }, [id])

  // Cancel any pending sentiment-poll reloads if the user leaves the page.
  useEffect(() => () => { reloadTimers.current.forEach(clearTimeout); reloadTimers.current = [] }, [])

  // Extract the actual post so it can be called from the live path and the replay handler.
  async function postReview({ storeId, rating: r, text }) {
    if (storeId !== id) return   // replayed for a different store — skip silently
    const optimistic = { id: '__pending', user_name: user?.name || 'You', rating: r, text, sentiment: null, _pending: true }
    setPendingReview(optimistic)
    setDraft(''); setRating(0)
    setSubmitting(true)
    try {
      await api.addReview(storeId, r, text)
      await load()
      setPendingReview(null)
      reloadTimers.current.push(setTimeout(load, 3000), setTimeout(load, 7000))
    } catch (e) {
      setPendingReview(null)
      setDraft(text); setRating(r)
      alert(e.message)
    } finally { setSubmitting(false) }
  }

  // Register the pending-action handler so a guest's draft is posted after login.
  // Runs before resumePendingAction() below, so the action is found on first try.
  useEffect(() => registerActionHandler('post_review', postReview), [id])

  // If the user just logged in and returned here (via ?next=), replay any queued review.
  useEffect(() => { if (user) resumePendingAction() }, [user])

  if (error) return <div className="store-wrap"><p style={{ color: 'var(--sent-neg)' }}>{error}</p></div>
  if (!store) return <div className="store-wrap" style={{ display: 'grid', placeItems: 'center', minHeight: 300 }}><span className="muted">Loading…</span></div>

  const ss = store.sentiment_summary || { positive: 0, neutral: 0, negative: 0, total: 0 }
  const cats = Array.isArray(store.categories)
    ? store.categories
    : String(store.categories || '').split(',').map(s => s.trim()).filter(Boolean)
  const isOpen = store.is_open_now
  const livePreview = previewSentiment(draft)

  async function onSave() {
    const nowSaved = toggleSaved(store.id)
    setSaved(nowSaved)
    if (nowSaved && user) { try { await api.saveStore(store.id) } catch {} }
  }

  function submitReview() {
    if (!rating) return
    const payload = { storeId: id, rating, text: draft }
    guard(() => postReview(payload), {
      pending: { type: 'post_review', payload },
    })
  }

  return (
    <div className="store-wrap">
      <Link to="/explore" className="muted" style={{ display: 'inline-block', marginBottom: 14, fontSize: 12.5, fontWeight: 600 }}>← Back to explore</Link>

      {/* HEADER CARD */}
      <div className="card store-header">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <div className="anton" style={{ fontSize: 38, color: 'var(--ink)', lineHeight: 1 }}>{(store.name || '').toUpperCase()}</div>
            {isOpen != null && (
              <span style={{ padding: '4px 10px', borderRadius: 14, background: isOpen ? '#e6f7ec' : 'var(--line-2)', color: isOpen ? '#16a34a' : 'var(--muted-2)', fontSize: 11, fontWeight: 700 }}>
                {isOpen ? 'OPEN NOW' : 'CLOSED'}
              </span>
            )}
          </div>
          {cats.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 8 }}>
              {cats.map(c => <span key={c} className="tag-chip">{c}</span>)}
            </div>
          )}
          {store.notes && <p style={{ marginTop: 14, color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.6, maxWidth: 560 }}>{store.notes}</p>}
          <div className="store-meta-grid">
            {store.open_time && <div className="store-meta-item"><span className="section-eyebrow">Hours</span>{store.open_time}–{store.close_time || '?'}</div>}
            {store.price_min != null && <div className="store-meta-item"><span className="section-eyebrow">Price range</span>₹{store.price_min}–{store.price_max}</div>}
            {store.phone && <div className="store-meta-item"><span className="section-eyebrow">Phone</span>{store.phone}</div>}
            {store.instagram && <div className="store-meta-item"><span className="section-eyebrow">Instagram</span><a href={`https://instagram.com/${store.instagram.replace(/^@/, '')}`} target="_blank" rel="noreferrer noopener">{store.instagram}</a></div>}
          </div>
        </div>
        <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, width: 150 }}>
          <ScoreRing score={store.experience_score} />
          <button onClick={onSave} className="save-btn">
            {saved ? '✓ Saved' : '♡ Save store'}
          </button>
        </div>
      </div>

      {/* TWO COLUMN */}
      <div className="store-two-col">
        {/* REVIEWS */}
        <section className="card" style={{ padding: 22, animation: 'ffFadeUp .3s ease .05s both' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
            <div className="anton" style={{ fontSize: 22, color: 'var(--ink)' }}>COMMUNITY REVIEWS</div>
            <span className="muted" style={{ fontSize: 12, fontWeight: 600 }}>{(store.reviews || []).length + (pendingReview ? 1 : 0)} reviews</span>
          </div>

          {ss.total > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', height: 10, borderRadius: 6, overflow: 'hidden' }}>
                <span style={{ flex: ss.positive || .01, background: 'var(--score-green)' }} />
                <span style={{ flex: ss.neutral || .01, background: 'var(--muted-2)' }} />
                <span style={{ flex: ss.negative || .01, background: 'var(--score-red)' }} />
              </div>
              <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11.5, color: 'var(--muted)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--score-green)' }} /> {ss.positive}% positive</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--muted-2)' }} /> {ss.neutral}% neutral</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}><span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--score-red)' }} /> {ss.negative}% negative</span>
              </div>
            </div>
          )}

          <div style={{ marginTop: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
            {[...(pendingReview ? [pendingReview] : []), ...(store.reviews || [])].map(r => {
              const flagged = isAnomalous(r.text)
              const bd = sentBadge(r.sentiment)
              return (
                <div key={r.id} className={`review-item ${flagged ? 'flagged' : ''}`} style={r._pending ? { opacity: .6 } : undefined}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div className="review-avatar">{(r.user_name || 'A')[0]}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{r.user_name || 'Anon'}</div>
                    <div style={{ color: '#f59e0b', fontSize: 12, letterSpacing: 1 }}>{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</div>
                    {r.sentiment && <span className="score-pill" style={{ marginLeft: 'auto', background: bd.bg, color: bd.ink, fontSize: 10 }}>{bd.label}</span>}
                  </div>
                  <p style={{ marginTop: 8, color: 'var(--muted)', fontSize: 12.5, lineHeight: 1.55 }}>{r.text}</p>
                  {flagged && (
                    <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--sent-flag)', fontSize: 11, fontWeight: 600 }}>
                      ⚠ Flagged as anomalous by our review model
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* COMPOSER — shown to all; guests are redirected to login with draft queued */}
          <div style={{ marginTop: 20, paddingTop: 18, borderTop: '1px solid var(--line-2)' }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)', marginBottom: 9 }}>Write a review</div>
            <div style={{ display: 'flex', gap: 4, marginBottom: 10 }}>
              {[1,2,3,4,5].map(n => (
                <button key={n} className="star-btn" type="button"
                  aria-label={`Rate ${n} star${n > 1 ? 's' : ''}`}
                  aria-pressed={n <= rating}
                  style={{ color: n <= rating ? '#f59e0b' : 'var(--muted-2)' }} onClick={() => setRating(n)}>
                  {n <= rating ? '★' : '☆'}
                </button>
              ))}
            </div>
            <textarea className="input textarea" rows={3} placeholder="Share your find…"
              value={draft} onChange={e => setDraft(e.target.value)}
              style={{ resize: 'vertical' }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 10 }}>
              <button onClick={submitReview} disabled={submitting || !rating}
                style={{ padding: '10px 18px', border: 0, borderRadius: 11, background: 'var(--nav)', color: '#fff', fontSize: 13, fontWeight: 700, transition: 'background .18s ease' }}>
                {submitting ? 'Posting…' : user ? 'Post review' : 'Log in to post'}
              </button>
              {livePreview && (
                <span style={{ fontSize: 12, fontWeight: 600, color: livePreview.color }}>
                  Live sentiment: {livePreview.label}
                </span>
              )}
            </div>
            {!user && rating > 0 && (
              <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Your review will be posted after you log in.</p>
            )}
          </div>
        </section>

        {/* SIMILAR */}
        <aside className="card" style={{ padding: 22, animation: 'ffFadeUp .3s ease .1s both' }}>
          <div className="anton" style={{ fontSize: 20, color: 'var(--ink)', lineHeight: 1.05 }}>SHOPPERS<br />ALSO LIKED</div>
          <div className="muted" style={{ marginTop: 4, fontSize: 11.5 }}>Collaborative filtering</div>
          <div style={{ marginTop: 15, display: 'flex', flexDirection: 'column', gap: 11 }}>
            {(store.similar || []).map(s => <StoreCard key={s.id} store={s} match={s.match_pct} />)}
          </div>
        </aside>
      </div>
    </div>
  )
}

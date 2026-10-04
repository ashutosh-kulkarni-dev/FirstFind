import { Link } from 'react-router-dom'

export function scoreClass(score) {
  if (score == null) return 'score-none'
  if (score >= 4.0) return 'score-green'
  if (score >= 3.0) return 'score-amber'
  return 'score-red'
}

export default function StoreCard({ store, compact = false }) {
  const s = store
  const openState = s.is_open_now === true ? 'yes' : s.is_open_now === false ? 'no' : 'unknown'
  return (
    <Link to={`/store/${s.id}`} className="card store-card">
      <div className="head">
        <div>
          <h3>{s.name}</h3>
          <div className="area">📍 {s.area}{s.distance_km != null && ` · ${s.distance_km} km`}</div>
        </div>
        <span className={`score-pill ${scoreClass(s.experience_score)}`}>
          {s.experience_score != null ? `★ ${s.experience_score.toFixed(1)}` : 'new'}
        </span>
      </div>
      {!compact && s.categories?.length > 0 && (
        <div className="tags">
          {s.categories.slice(0, 4).map(c => <span key={c} className="tag">{c}</span>)}
        </div>
      )}
      <div className="meta-row">
        <span>
          <span className={`open-dot open-${openState}`} />
          {openState === 'yes' ? 'Open now' : openState === 'no' ? 'Closed' : 'Hours unknown'}
        </span>
        {s.price_min && <span>₹{s.price_min}–{s.price_max}</span>}
        {s.review_count > 0 && <span>{s.review_count} reviews</span>}
      </div>
    </Link>
  )
}

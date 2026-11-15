import { scoreHex } from '../lib/score'

// Small colored rating chip reused across cards, popups and lists.
// Shows the AI score when the store has one. Until it does (no reviews
// ingested yet), falls back to the store's Google rating, marked with a "G".
export default function ScorePill({ score, googleRating, className = '' }) {
  const hasAi = score != null
  const shown = hasAi ? score : googleRating
  if (shown == null) {
    return (
      <span className={`score-pill ${className}`} title="No reviews yet"
        style={{ background: 'var(--line-2)', color: 'var(--muted-2)' }}>
        No rating yet
      </span>
    )
  }
  const c = scoreHex(shown)
  return (
    <span className={`score-pill ${className}`} style={{ background: `${c}22`, color: c }}
      title={hasAi ? 'AI score: star ratings blended with review sentiment'
        : 'Google rating — no AI score yet'}>
      ⭐ {Number(shown).toFixed(1)}{!hasAi && <span style={{ marginLeft: 4, opacity: .7, fontSize: '.85em' }}>G</span>}
    </span>
  )
}

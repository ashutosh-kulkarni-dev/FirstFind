import { scoreHex } from '../lib/score'

// Small colored rating chip reused across cards, popups and lists.
export default function ScorePill({ score, className = '' }) {
  const c = scoreHex(score)
  const val = score == null ? '—' : Number(score).toFixed(1)
  return (
    <span className={`score-pill ${className}`} style={{ background: `${c}22`, color: c }}>
      ⭐ {val}
    </span>
  )
}

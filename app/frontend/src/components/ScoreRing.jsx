import { scoreHex } from '../lib/score'

// Circular score gauge for the store header (from FirstFind Store mockup).
// AI score when available; otherwise the Google rating, labelled as such.
export default function ScoreRing({ score, googleRating, size = 120 }) {
  const hasAi = score != null
  const shown = hasAi ? score : googleRating
  const r = 52, C = 2 * Math.PI * r
  const pct = shown == null ? 0 : Math.max(0, Math.min(1, shown / 5))
  const offset = C * (1 - pct)
  const c = scoreHex(shown)
  const label = hasAi ? 'AI SCORE' : shown != null ? 'GOOGLE RATING' : 'NO RATING YET'
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg viewBox="0 0 120 120" style={{ width: '100%', height: '100%', transform: 'rotate(-90deg)' }}>
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--line-2)" strokeWidth="11" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={c} strokeWidth="11" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset .8s cubic-bezier(.2,.8,.2,1)' }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div className="anton" style={{ fontSize: 30, color: 'var(--ink)', lineHeight: 1 }}>
          {shown == null ? '—' : Number(shown).toFixed(1)}
        </div>
        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.5px', color: 'var(--muted-2)' }}>{label}</div>
      </div>
    </div>
  )
}

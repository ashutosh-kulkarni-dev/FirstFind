import { scoreHex } from '../lib/score'

// Circular AI-score gauge for the store header (from FirstFind Store mockup).
export default function ScoreRing({ score, size = 120 }) {
  const r = 52, C = 2 * Math.PI * r
  const pct = score == null ? 0 : Math.max(0, Math.min(1, score / 5))
  const offset = C * (1 - pct)
  const c = scoreHex(score)
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
          {score == null ? '—' : Number(score).toFixed(1)}
        </div>
        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.5px', color: 'var(--muted-2)' }}>AI SCORE</div>
      </div>
    </div>
  )
}

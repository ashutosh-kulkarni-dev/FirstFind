// AI-score legend block (Explore sidebar). Mirrors the mockup and the marker
// colours from lib/score.js so the map and the key stay in sync.
const ROWS = [
  { c: 'var(--score-green)', t: '4.5–5.0 · Exceptional' },
  { c: 'var(--score-lime)', t: '4.0–4.5 · Great' },
  { c: 'var(--score-amber)', t: '3.5–4.0 · Good' },
  { c: 'var(--score-red)', t: 'Below 3.5' },
  { c: 'var(--score-none)', t: 'Unrated' },
]

export default function Legend() {
  return (
    <div>
      <div className="section-eyebrow" style={{ marginBottom: 7 }}>AI score legend</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {ROWS.map(r => (
          <div key={r.t} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11.5, color: 'var(--muted)' }}>
            <span style={{ width: 11, height: 11, borderRadius: '50%', background: r.c }} /> {r.t}
          </div>
        ))}
      </div>
    </div>
  )
}

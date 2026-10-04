import { RADIUS_PRESETS, reachLabel } from '../../lib/zonesView'

// Cluster radius controls. `radius` prop is radiusKm (internal); all display
// uses diameter = radius * 2. Slider range: 600 m–7 km diameter.
export default function DrawControls({ radius, onRadius, onGps }) {
  const diameter = radius * 2
  const displayDiameter = diameter < 1
    ? Math.round(diameter * 1000) + ' m'
    : (diameter % 1 === 0 ? diameter + ' km' : diameter.toFixed(1) + ' km')
  const pct = ((diameter - 0.6) / 6.4 * 100) + '%'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <button
        onClick={onGps}
        style={{
          padding: '9px 14px',
          border: '1px solid var(--line)',
          borderRadius: 10,
          background: 'var(--surface)',
          color: 'var(--brand-blue)',
          fontSize: 13,
          fontWeight: 700,
          whiteSpace: 'nowrap',
          cursor: 'pointer',
        }}
      >
        ◎ Centre on my location
      </button>

      <div style={{ border: '1px solid var(--line)', borderRadius: 14, background: 'var(--surface-2)', padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--muted)' }}>Cluster diameter</span>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 22, color: 'var(--ink)' }}>
            {displayDiameter}
          </span>
        </div>

        <input
          type="range"
          min={0.6}
          max={7}
          step={0.3}
          value={diameter}
          onChange={e => onRadius(parseFloat(e.target.value) / 2)}
          className="rng"
          style={{ '--pct': pct, width: '100%', display: 'block' }}
        />

        <div style={{ marginTop: 6, fontSize: 11.5, color: 'var(--muted-2)' }}>
          {reachLabel(radius)}
        </div>

        <div style={{ display: 'flex', gap: 6, marginTop: 12, flexWrap: 'wrap' }}>
          {RADIUS_PRESETS.map(p => {
            const active = Math.abs(radius - p.km) < 0.01
            return (
              <button
                key={p.label}
                onClick={() => onRadius(p.km)}
                style={{
                  padding: '5px 12px',
                  borderRadius: 20,
                  fontSize: 12,
                  fontWeight: 700,
                  border: '1px solid',
                  background: active ? 'var(--brand-blue-2)' : 'var(--surface)',
                  color: active ? '#fff' : 'var(--muted)',
                  borderColor: active ? 'var(--brand-blue-2)' : 'var(--line)',
                  cursor: 'pointer',
                  transition: 'all .15s',
                }}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

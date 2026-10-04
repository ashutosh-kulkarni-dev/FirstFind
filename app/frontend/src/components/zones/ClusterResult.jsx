function StoreRow({ store, onFocusStore }) {
  const sub = [store.area, store.distKm != null ? store.distKm.toFixed(1) + ' km' : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <div
      onClick={() => onFocusStore && onFocusStore(store.id)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 0',
        borderBottom: '1px solid var(--line-2)',
        cursor: 'pointer',
      }}
    >
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: 'var(--muted)', flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {(store.name || '').toUpperCase()}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted-2)' }}>{sub}</div>
      </div>
    </div>
  )
}

// Renders the stores inside the movable cluster. `stores` is already filtered to
// the radius (and honours the sidebar filters) by the page; this component only
// presents them.
export default function ClusterResult({ stores, radiusKm, onFocusStore }) {
  const empty = stores.length === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ padding: 15, border: '1px solid var(--line)', borderRadius: 14, background: 'var(--surface)' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
          <span style={{ fontFamily: 'var(--font-display)', fontSize: 18, color: 'var(--ink)', flex: 1 }}>
            YOUR CLUSTER
          </span>
          {radiusKm != null && (
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--brand-blue-2)' }}>
              {radiusKm} km
            </span>
          )}
        </div>

        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: 26, color: 'var(--ink)' }}>{stores.length}</div>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.4px' }}>Stores in range</div>
        </div>
      </div>

      <div style={{
        padding: 12,
        border: '1.5px dashed var(--line)',
        borderRadius: 12,
        background: 'var(--surface-2)',
        color: 'var(--muted)',
        fontSize: 12,
        lineHeight: 1.5,
      }}>
        Double-click the map to drop a new centre, drag the pin to move it, or use the radius slider.
      </div>

      {empty ? (
        <div style={{ padding: 14, color: 'var(--muted)', fontSize: 13, textAlign: 'center' }}>
          No stores in this radius.
        </div>
      ) : (
        <div style={{ padding: '0 4px' }}>
          {stores.map(store => (
            <StoreRow key={store.id} store={store} onFocusStore={onFocusStore} />
          ))}
        </div>
      )}
    </div>
  )
}

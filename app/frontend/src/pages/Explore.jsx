import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useRequireAuth } from '../auth/RequireAuth'
import { registerActionHandler, resumePendingAction } from '../auth/pendingAction'
import { parseZoneParams, normalizeStore } from '../lib/zonesView'
import { storesWithinRadius } from '../lib/cluster'
import MapExplorer from '../components/MapExplorer'
import DrawControls from '../components/zones/DrawControls'
import ClusterResult from '../components/zones/ClusterResult'
import ScorePill from '../components/ScorePill'

const BLR_DEFAULT = [12.9716, 77.5946]

export default function Explore() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user } = useAuth()
  const guard = useRequireAuth()

  // Deep-link support: "Open on map" (Lists) and the chat open_zones action send
  // ?lat&lng&radius, which pre-opens the cluster. Parsed once for initial state.
  const init = useRef(parseZoneParams(searchParams)).current

  const [areas, setAreas] = useState([])
  const [stores, setStores] = useState([])
  const [metroLines, setMetroLines] = useState([])
  const [metroOn, setMetroOn] = useState(true)

  const [q, setQ] = useState('')
  const [area, setArea] = useState('')
  const [openOnly, setOpenOnly] = useState(false)
  const [selectedId, setSelectedId] = useState(null)

  // Cluster: null centre = off. Enabled by double-clicking the map (or a deep-link).
  const [center, setCenter] = useState(init.center)
  const [radiusKm, setRadiusKm] = useState(init.radiusKm || 0.3)

  // Save-list modal state
  const [savePrompt, setSavePrompt] = useState(false)
  const [listName, setListName] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saving, setSaving] = useState(false)

  // Saved lists panel (sidebar bottom)
  const [myLists, setMyLists] = useState(null) // null = not yet fetched

  const [mapFull, setMapFull] = useState(false)

  useEffect(() => {
    api.areas().then(setAreas).catch(() => {})
    api.metroStations().then(r => setMetroLines(r?.lines ?? [])).catch(() => {})
  }, [])

  // Fetch saved lists whenever auth state changes (login/logout)
  useEffect(() => {
    if (user) {
      api.lists().then(setMyLists).catch(() => setMyLists([]))
    } else {
      setMyLists(null)
    }
  }, [user])

  // Replay a guest's queued "save list" after they log in.
  useEffect(() => registerActionHandler('save_list', async (payload) => {
    await api.createList({ name: payload.source_label || 'My saved list', ...payload }).catch(() => {})
    navigate('/lists')
  }), [navigate])
  useEffect(() => { if (user) resumePendingAction() }, [user])

  // Filtered store set — the single source of truth for both dots and cluster.
  useEffect(() => {
    const params = {}
    if (q) params.q = q
    if (area) params.area = area
    const controller = new AbortController()
    const t = setTimeout(() => {
      api.stores(params, { signal: controller.signal })
        .then(r => { setStores((r.stores || []).map(normalizeStore)); setSelectedId(null) })
        .catch(() => {}) // includes AbortError from a superseded search
    }, 200)
    return () => { clearTimeout(t); controller.abort() }
  }, [q, area])

  // "Open now only" is a client-side filter on the already-fetched set.
  const shown = useMemo(() => (openOnly ? stores.filter(s => s.open) : stores), [stores, openOnly])

  const selected = useMemo(() => shown.find(s => s.id === selectedId), [shown, selectedId])

  // Cluster honours the active filters: computed from the shown stores.
  const clusterStores = useMemo(
    () => storesWithinRadius(shown, center, radiusKm),
    [shown, center, radiusKm],
  )

  const reset = () => { setQ(''); setArea(''); setOpenOnly(false) }

  const handleGps = () => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      pos => setCenter([pos.coords.latitude, pos.coords.longitude]),
      () => setCenter(BLR_DEFAULT),
    )
  }

  function openSavePrompt() {
    const payload = {
      store_ids: clusterStores.map(s => s.id),
      center_lat: center[0], center_lng: center[1],
      radius_km: radiusKm, source_label: area || 'My thrift run',
    }
    guard(() => {
      setListName(payload.source_label)
      setSaveError('')
      setSavePrompt(true)
    }, { pending: { type: 'save_list', payload } })
  }

  async function confirmSave() {
    const name = listName.trim()
    if (!name) { setSaveError('Please give your list a name.'); return }
    setSaving(true); setSaveError('')
    try {
      await api.createList({
        name,
        store_ids: clusterStores.map(s => s.id),
        center_lat: center[0], center_lng: center[1],
        radius_km: radiusKm, source_label: area || name,
      })
      setSavePrompt(false)
      navigate('/lists')
    } catch (e) {
      setSaveError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const badge = center
    ? 'CLUSTER · DRAG PIN OR DOUBLE-CLICK TO MOVE'
    : 'DOUBLE-CLICK THE MAP TO START A CLUSTER'

  return (
    <div className="explore-shell" style={mapFull ? { gridTemplateColumns: '1fr' } : undefined}>

      {/* Save-list name prompt modal */}
      {savePrompt && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 300, display: 'grid', placeItems: 'center', background: 'rgba(0,0,0,.4)' }}
          onClick={() => setSavePrompt(false)}>
          <div style={{ background: 'var(--surface)', borderRadius: 16, padding: 24, width: 'min(360px, 90vw)', boxShadow: '0 8px 40px rgba(0,0,0,.25)' }}
            onClick={e => e.stopPropagation()}>
            <div className="anton" style={{ fontSize: 20, color: 'var(--ink)', marginBottom: 14 }}>NAME THIS LIST</div>
            <input className="input" autoFocus
              placeholder="My thrift run"
              value={listName} onChange={e => setListName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && confirmSave()}
              style={{ width: '100%' }} />
            {saveError && (
              <p style={{ marginTop: 8, fontSize: 12, color: 'var(--sent-neg)', fontWeight: 600 }}>{saveError}</p>
            )}
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button className="btn btn-primary" style={{ flex: 1, justifyContent: 'center' }}
                onClick={confirmSave} disabled={saving}>
                {saving ? 'Saving…' : 'Save list'}
              </button>
              <button className="btn btn-light" onClick={() => setSavePrompt(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}

      <aside className="explore-aside" style={mapFull ? { display: 'none' } : undefined}>
        <div style={{ padding: '22px 22px 16px', flexShrink: 0 }}>
          <div className="anton" style={{ fontSize: 30, color: 'var(--ink)', lineHeight: .95 }}>EXPLORE<br />STORES</div>
          <p className="muted" style={{ marginTop: 9, fontSize: 12.5, lineHeight: 1.5 }}>
            Verified thrift &amp; second-hand stores across Bengaluru. Search, browse the map, or
            double-click to cluster stores within a walkable radius.
          </p>
        </div>

        <div style={{ padding: '0 22px', display: 'flex', flexDirection: 'column', gap: 13, flexShrink: 0 }}>
          <label>
            <span className="field-label">Search</span>
            <input className="input" placeholder="Store name or location…" value={q} onChange={e => setQ(e.target.value)} />
          </label>
          <label>
            <span className="field-label">Area</span>
            <select className="select" value={area} onChange={e => setArea(e.target.value)}>
              <option value="">All areas</option>
              {areas.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', userSelect: 'none' }}>
            <input type="checkbox" checked={openOnly} onChange={e => { setOpenOnly(e.target.checked); setSelectedId(null) }}
              style={{ width: 16, height: 16, accentColor: 'var(--brand-blue-2)', cursor: 'pointer' }} />
            <span style={{ fontSize: 13, color: 'var(--muted)', fontWeight: 500 }}>Open now only</span>
          </label>
        </div>

        <div style={{ margin: '18px 22px 8px', paddingTop: 16, borderTop: '1px solid var(--line-2)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <span className="anton" style={{ fontSize: 18, color: 'var(--ink)' }}>{shown.length} RESULTS</span>
          <button className="btn" style={{ padding: '5px 11px', borderRadius: 16, fontSize: 11 }} onClick={reset}>Reset</button>
        </div>

        {/* Distance slider — always visible, replaces the old AI score legend */}
        <div style={{ padding: '0 22px 8px', flexShrink: 0 }}>
          <DrawControls radius={radiusKm} onRadius={setRadiusKm} onGps={handleGps} />
        </div>

        {/* Cluster results — only once the user drops a pin */}
        <div style={{ flex: 1, padding: '0 22px 12px', overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {center ? (
            <>
              <ClusterResult stores={clusterStores} radiusKm={radiusKm} onFocusStore={id => navigate(`/store/${id}`)} />
              <div style={{ display: 'flex', gap: 8 }}>
                {clusterStores.length > 0 && (
                  <button onClick={openSavePrompt}
                    style={{ flex: 1, border: '1px solid var(--brand-blue-2)', borderRadius: 20, padding: '7px 12px', fontSize: 12, fontWeight: 700, color: 'var(--brand-blue-2)', background: 'transparent', cursor: 'pointer' }}>
                    + Save list
                  </button>
                )}
                <button onClick={() => setCenter(null)}
                  style={{ border: '1px solid var(--line)', borderRadius: 20, padding: '7px 12px', fontSize: 12, fontWeight: 700, color: 'var(--muted)', background: 'transparent', cursor: 'pointer' }}>
                  Clear
                </button>
              </div>
            </>
          ) : (
            <div style={{ padding: 14, border: '1.5px dashed var(--line)', borderRadius: 12, background: 'var(--surface-2)', color: 'var(--muted)', fontSize: 12.5, lineHeight: 1.5, textAlign: 'center' }}>
              Double-click anywhere on the map to cluster stores within this diameter.
            </div>
          )}
        </div>

        {selected && (
          <div style={{ padding: '14px 22px', borderTop: '1px solid var(--line-2)', flexShrink: 0 }} className="fade-up">
            <div className="section-eyebrow" style={{ color: 'var(--brand-blue-2)', marginBottom: 4 }}>Selected store</div>
            <div className="anton" style={{ fontSize: 19, color: 'var(--ink)' }}>{selected.name}</div>
            <div className="muted" style={{ marginTop: 2, fontSize: 12 }}>{[selected.area, selected.cat].filter(Boolean).join(' · ')}</div>
            <div style={{ marginTop: 7, display: 'flex', alignItems: 'center', gap: 8 }}>
              <ScorePill score={selected.score} />
              {selected.open != null && (
                <span style={{ fontSize: 11.5, fontWeight: 600, color: selected.open ? 'var(--sent-pos)' : 'var(--muted-2)' }}>
                  {selected.open ? 'Open now' : 'Closed'}
                </span>
              )}
            </div>
            <Link to={`/store/${selected.id}`} style={{ display: 'inline-block', marginTop: 9, fontSize: 12.5, fontWeight: 700 }}>View store →</Link>
          </div>
        )}

        <label style={{ padding: '12px 22px', borderTop: '1px solid var(--line-2)', background: 'var(--surface)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer', userSelect: 'none' }}>
          <input type="checkbox" checked={metroOn} onChange={e => setMetroOn(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: 'var(--brand-blue-2)', cursor: 'pointer' }} />
          <span style={{ fontSize: 12.5, color: 'var(--muted)', fontWeight: 500 }}>Show Namma Metro lines</span>
        </label>

        {/* YOUR LISTS panel */}
        <div style={{ padding: '14px 22px 18px', borderTop: '1px solid var(--line-2)', flexShrink: 0 }}>
          <div className="section-eyebrow" style={{ marginBottom: 8 }}>Your lists</div>
          {user ? (
            myLists === null ? (
              <span className="muted" style={{ fontSize: 12 }}>Loading…</span>
            ) : myLists.length === 0 ? (
              <div style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5 }}>
                No lists yet. Double-click the map to cluster stores, then save as a list.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {myLists.slice(0, 4).map(l => (
                  <Link key={l.id} to={`/lists`}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 11px', border: '1px solid var(--line)', borderRadius: 10, background: 'var(--surface-2)', textDecoration: 'none', transition: 'border-color .18s ease' }}
                    onMouseOver={e => e.currentTarget.style.borderColor = 'var(--brand-blue-2)'}
                    onMouseOut={e => e.currentTarget.style.borderColor = 'var(--line)'}>
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>{l.name}</span>
                    <span style={{ fontSize: 11, color: 'var(--muted-2)', fontWeight: 500, flexShrink: 0, marginLeft: 6 }}>{l.store_count} store{l.store_count !== 1 ? 's' : ''}</span>
                  </Link>
                ))}
                {myLists.length > 4 && (
                  <Link to="/lists" style={{ fontSize: 12, color: 'var(--brand-blue-2)', fontWeight: 600, marginTop: 2 }}>
                    View all {myLists.length} lists →
                  </Link>
                )}
              </div>
            )
          ) : (
            <div style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.6 }}>
              <Link to="/login" style={{ color: 'var(--brand-blue)', fontWeight: 600 }}>Log in</Link> or{' '}
              <Link to="/register" style={{ color: 'var(--brand-blue)', fontWeight: 600 }}>create an account</Link>
              {' '}to save lists and come back later.
            </div>
          )}
        </div>
      </aside>

      <section className="explore-map">
        <MapExplorer
          stores={shown}
          selectedId={selectedId}
          onSelectStore={setSelectedId}
          onViewStore={id => navigate(`/store/${id}`)}
          clusterCenter={center}
          radiusKm={radiusKm}
          onMoveCenter={setCenter}
          metroLines={metroLines}
          metroOn={metroOn}
          badge={badge}
          fullscreen={mapFull}
          onToggleFullscreen={() => setMapFull(f => !f)}
        />
      </section>

      {/* Fullscreen overlay: DrawControls panel pinned to the right of the map */}
      {mapFull && (
        <div className="explore-full-panel">
          <DrawControls radius={radiusKm} onRadius={setRadiusKm} onGps={handleGps} />
        </div>
      )}
    </div>
  )
}

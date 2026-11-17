import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { useRequireAuth } from '../auth/RequireAuth'
import { registerActionHandler, resumePendingAction } from '../auth/pendingAction'
import { parseZoneParams, normalizeStore } from '../lib/zonesView'
import { storesWithinRadius } from '../lib/cluster'
import MapExplorer from '../components/MapExplorer'
import DrawControls from '../components/zones/DrawControls'
import ClusterPanel from './explore/ClusterPanel'
import FilterPanel from './explore/FilterPanel'
import MyListsPanel from './explore/MyListsPanel'
import ResultsList from './explore/ResultsList'
import SaveListModal from './explore/SaveListModal'
import SelectedStoreCard from './explore/SelectedStoreCard'

const BLR_DEFAULT = [12.9716, 77.5946]

// The map page. This file owns the state and data loading; what is drawn in
// the sidebar lives in ./explore/*.
export default function Explore() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user } = useAuth()
  const guard = useRequireAuth()

  // Deep-link support: "Open on map" (Lists) and the chat open_zones action send
  // ?lat&lng&radius, which pre-opens the cluster. Parsed once for initial state.
  const init = useRef(parseZoneParams(searchParams)).current

  const [areas, setAreas] = useState([])
  const [facets, setFacets] = useState({ store_types: [], tags: [] })
  const [stores, setStores] = useState([])
  const [metroLines, setMetroLines] = useState([])
  const [metroOn, setMetroOn] = useState(true)

  // Filters start from the address bar (?q&area&type&tag&open) and are written
  // back to it, so Back, refresh and shared links keep them.
  const [q, setQ] = useState(searchParams.get('q') || '')
  const [area, setArea] = useState(searchParams.get('area') || '')
  const [storeType, setStoreType] = useState(searchParams.get('type') || '')
  const [tag, setTag] = useState(searchParams.get('tag') || '')
  const [openOnly, setOpenOnly] = useState(searchParams.get('open') === '1')
  const [selectedId, setSelectedId] = useState(null)
  const [hoveredId, setHoveredId] = useState(null)   // shared by the list and the map

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
    api.facets().then(setFacets).catch(() => {})
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
    if (storeType) params.store_type = storeType
    if (tag) params.tag = tag
    const controller = new AbortController()
    const t = setTimeout(() => {
      api.stores(params, { signal: controller.signal })
        .then(r => { setStores((r.stores || []).map(normalizeStore)); setSelectedId(null) })
        .catch(() => {}) // includes AbortError from a superseded search
    }, 200)
    return () => { clearTimeout(t); controller.abort() }
  }, [q, area, storeType, tag])

  useEffect(() => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      const put = (key, value) => (value ? next.set(key, value) : next.delete(key))
      put('q', q); put('area', area); put('type', storeType); put('tag', tag); put('open', openOnly ? '1' : '')
      return next
    }, { replace: true })
  }, [q, area, storeType, tag, openOnly, setSearchParams])

  // "Open now only" is a client-side filter on the already-fetched set.
  const shown = useMemo(() => {
    const kindLabel = Object.fromEntries(facets.store_types.map(k => [k.value, k.label]))
    const tagLabel = Object.fromEntries(facets.tags.map(t => [t.value, t.label]))
    return (openOnly ? stores.filter(s => s.open) : stores).map(s => ({
      ...s,
      kindLabel: kindLabel[s.storeType] || '',
      tagLabels: s.tags.map(t => tagLabel[t]).filter(Boolean),
    }))
  }, [stores, openOnly, facets])

  const selected = useMemo(() => shown.find(s => s.id === selectedId), [shown, selectedId])

  // Cluster honours the active filters: computed from the shown stores.
  const clusterStores = useMemo(
    () => storesWithinRadius(shown, center, radiusKm),
    [shown, center, radiusKm],
  )

  const reset = () => { setQ(''); setArea(''); setStoreType(''); setTag(''); setOpenOnly(false) }

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

  // The map re-fits when a filter is picked — not when the search text changes.
  const fitKey = [area, storeType, tag, openOnly ? 'open' : ''].join('|')

  const badge = center
    ? 'CLUSTER · DRAG PIN OR DOUBLE-CLICK TO MOVE'
    : 'DOUBLE-CLICK THE MAP TO START A CLUSTER'

  return (
    <div className={mapFull ? 'explore-shell explore-shell-full' : 'explore-shell'}>

      {savePrompt && (
        <SaveListModal name={listName} onName={setListName} error={saveError} saving={saving}
          onConfirm={confirmSave} onCancel={() => setSavePrompt(false)} />
      )}

      <aside className="explore-aside">
        <div className="explore-head">
          <div className="anton explore-title">EXPLORE<br />STORES</div>
          <p className="muted explore-intro">
            Verified thrift &amp; second-hand stores across Bengaluru. Search, browse the map, or
            double-click to cluster stores within a walkable radius.
          </p>
        </div>

        <FilterPanel q={q} onQ={setQ} area={area} onArea={setArea} areas={areas}
          storeType={storeType} onStoreType={setStoreType} kinds={facets.store_types}
          tag={tag} onTag={setTag} tags={facets.tags}
          openOnly={openOnly} onOpenOnly={v => { setOpenOnly(v); setSelectedId(null) }}
          count={shown.length} onReset={reset} />

        {/* Distance slider — always visible */}
        {/* Folded away until wanted, so the results list has room. Opens by
            itself once a cluster pin is on the map. */}
        <details className="explore-draw" open={!!center || undefined}>
          <summary>Group stores by distance</summary>
          <DrawControls radius={radiusKm} onRadius={setRadiusKm} onGps={handleGps} />
        </details>

        {/* The scrolling middle: the cluster once a pin is dropped, else the results */}
        <div className="explore-cluster">
          {center ? (
            <ClusterPanel stores={clusterStores} radiusKm={radiusKm}
              onOpenStore={id => navigate(`/store/${id}`)}
              onSave={openSavePrompt} onClear={() => setCenter(null)} />
          ) : (
            <>
              <ResultsList stores={shown} selectedId={selectedId} onSelect={setSelectedId}
                hoveredId={hoveredId} onHover={setHoveredId}
                onOpen={id => navigate(`/store/${id}`)} />
              <div className="explore-tip">Tip: double-click the map to group stores within the distance above.</div>
            </>
          )}
        </div>

        {/* With the results list showing, the highlighted row is the selection.
            The card is only needed while the cluster view replaces the list. */}
        {selected && center && <SelectedStoreCard store={selected} />}

        <label className="check-row explore-metro-toggle">
          <input type="checkbox" checked={metroOn} onChange={e => setMetroOn(e.target.checked)} />
          <span>Show Namma Metro lines</span>
        </label>

        <MyListsPanel user={user} lists={myLists} />
      </aside>

      <section className="explore-map">
        <MapExplorer
          stores={shown}
          selectedId={selectedId}
          hoveredId={hoveredId}
          onSelectStore={setSelectedId}
          onHoverStore={setHoveredId}
          fitKey={fitKey}
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

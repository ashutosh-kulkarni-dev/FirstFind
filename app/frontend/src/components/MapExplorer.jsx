import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { createDarkMap } from '../lib/map/leaflet'
import { drawCluster, drawMetro } from '../lib/map/zoneLayers'
import { StoreMarkers } from '../lib/map/storeMarkers'

const SETTLE_MS = 700   // after a search settles, re-fit only if no result is in view

// The single map for the Explore page: store dots (clustered when zoomed out) +
// an optional movable cluster ring + optional metro lines. Double-clicking the
// map sets (or relocates) the cluster centre; the centre pin can also be dragged.
//
// fitKey: the map zooms to fit the stores when this changes (a filter was
// picked), not on every new result set, so typing in search never re-zooms.
export default function MapExplorer({
  stores = [],
  selectedId,
  hoveredId,
  onSelectStore,
  onViewStore,
  onHoverStore,
  fitKey = '',
  clusterCenter,
  radiusKm,
  onMoveCenter,
  metroLines = [],
  metroOn,
  badge = 'BENGALURU · LIVE MAP',
  fullscreen = false,
  onToggleFullscreen,
}) {
  const elRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef(null)
  const lastFitRef = useRef(undefined)
  const clusterLayerRef = useRef(null)
  const metroLayerRef = useRef(null)
  // Keep the latest move handler reachable from the once-bound dblclick listener.
  const moveRef = useRef(onMoveCenter)
  useEffect(() => { moveRef.current = onMoveCenter }, [onMoveCenter])

  useEffect(() => {
    if (!elRef.current || mapRef.current) return
    const map = createDarkMap(elRef.current)
    map.doubleClickZoom.disable() // double-click is reserved for dropping the cluster centre
    markersRef.current = new StoreMarkers(L, map, {})
    clusterLayerRef.current = L.layerGroup().addTo(map)
    metroLayerRef.current = L.layerGroup().addTo(map)
    mapRef.current = map

    map.on('dblclick', e => moveRef.current && moveRef.current([e.latlng.lat, e.latlng.lng]))

    // Keep Leaflet's tile grid in sync with container size. Without this, any
    // layout change (fullscreen toggle, side-panel open, window resize) leaves
    // half the viewport blank or misaligned until the next pan.
    const firstFrame = requestAnimationFrame(() => map.invalidateSize())
    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(elRef.current)
    const onWinResize = () => map.invalidateSize()
    window.addEventListener('resize', onWinResize)

    return () => {
      cancelAnimationFrame(firstFrame)   // the map may be gone before the frame runs
      ro.disconnect()
      window.removeEventListener('resize', onWinResize)
      markersRef.current?.destroy()
      markersRef.current = null
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Fullscreen toggles the container via CSS; nudge Leaflet after the transition.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const t = setTimeout(() => map.invalidateSize(), 220)
    return () => clearTimeout(t)
  }, [fullscreen])

  useEffect(() => {
    markersRef.current?.setHandlers({ onSelect: onSelectStore, onView: onViewStore, onHover: onHoverStore })
  }, [onSelectStore, onViewStore, onHoverStore])

  // New store set: rebuild the dots. Zoom to fit only when the filters changed
  // (fitKey) — or, once a search settles, when none of its results is in view.
  const clusterOn = !!clusterCenter
  useEffect(() => {
    const map = mapRef.current, markers = markersRef.current
    if (!map || !markers) return
    markers.setStores(stores)
    const pts = markers.bounds()
    if (!pts.length || clusterOn) return
    const fit = () => map.fitBounds(pts, { padding: [50, 50], maxZoom: 14 })
    if (fitKey !== lastFitRef.current) {
      lastFitRef.current = fitKey
      fit()
      return
    }
    const t = setTimeout(() => {
      const view = map.getBounds()
      if (!pts.some(p => view.contains(p))) fit()
    }, SETTLE_MS)
    return () => clearTimeout(t)
  }, [stores, fitKey, clusterOn])

  // Selection and hover: only the highlighted dots change.
  useEffect(() => {
    markersRef.current?.setHighlight(selectedId || null, hoveredId || null)
  }, [selectedId, hoveredId, stores])

  // Bring a newly selected store into view (zooming in if it is inside a cluster).
  useEffect(() => {
    const map = mapRef.current, markers = markersRef.current
    if (!map || !markers || !selectedId) return
    const p = markers.position(selectedId)
    if (!p) return
    if (markers.isClustered(selectedId)) map.setView(p, 15, { animate: true })
    else if (!map.getBounds().pad(-0.15).contains(p)) map.panTo(p, { animate: true })
  }, [selectedId])

  useEffect(() => {
    const layer = clusterLayerRef.current
    if (!layer) return
    if (clusterCenter) {
      drawCluster(L, layer, { center: clusterCenter, radiusKm, onDragEnd: onMoveCenter })
    } else {
      layer.clearLayers()
    }
  }, [clusterCenter, radiusKm, onMoveCenter])

  useEffect(() => {
    const layer = metroLayerRef.current
    if (!layer) return
    if (metroOn) drawMetro(L, layer, metroLines)
    else layer.clearLayers()
  }, [metroOn, metroLines])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={elRef} style={{ position: 'absolute', inset: 0, background: 'var(--map-bg)' }} />
      <div style={{ position: 'absolute', top: 16, left: 16, zIndex: 500, padding: '7px 13px', borderRadius: 20, background: 'rgba(15,26,43,.82)', backdropFilter: 'blur(4px)', color: '#cfe4f5', fontSize: 11, fontWeight: 600, letterSpacing: '.4px' }}>
        {badge}
      </div>
      {onToggleFullscreen && (
        <button
          onClick={onToggleFullscreen}
          title={fullscreen ? 'Exit fullscreen' : 'Fullscreen map'}
          style={{
            position: 'absolute', top: 16, right: 16, zIndex: 500,
            width: 34, height: 34, border: 0, borderRadius: 8,
            background: 'rgba(15,26,43,.82)', backdropFilter: 'blur(4px)',
            color: '#cfe4f5', fontSize: 15, cursor: 'pointer',
            display: 'grid', placeItems: 'center',
            transition: 'background .18s ease',
          }}
          onMouseOver={e => e.currentTarget.style.background = 'rgba(20,120,209,.9)'}
          onMouseOut={e => e.currentTarget.style.background = 'rgba(15,26,43,.82)'}
        >
          <span style={{ fontSize: 13, lineHeight: 1 }}>{fullscreen ? '✕' : '⤢'}</span>
        </button>
      )}
    </div>
  )
}

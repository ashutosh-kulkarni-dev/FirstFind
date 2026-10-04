import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { createDarkMap } from '../lib/map/leaflet'
import { drawStores, drawCluster, drawMetro } from '../lib/map/zoneLayers'

// The single map for the Explore page: grey store dots + an optional movable
// cluster ring + optional metro lines. Double-clicking the map sets (or
// relocates) the cluster centre; the centre pin can also be dragged.
export default function MapExplorer({
  stores = [],
  selectedId,
  onSelectStore,
  onViewStore,
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
  const storeLayerRef = useRef(null)
  const clusterLayerRef = useRef(null)
  const metroLayerRef = useRef(null)
  // Keep the latest move handler reachable from the once-bound dblclick listener.
  const moveRef = useRef(onMoveCenter)
  useEffect(() => { moveRef.current = onMoveCenter }, [onMoveCenter])

  useEffect(() => {
    if (!elRef.current || mapRef.current) return
    const map = createDarkMap(elRef.current)
    map.doubleClickZoom.disable() // double-click is reserved for dropping the cluster centre
    storeLayerRef.current = L.layerGroup().addTo(map)
    clusterLayerRef.current = L.layerGroup().addTo(map)
    metroLayerRef.current = L.layerGroup().addTo(map)
    mapRef.current = map

    map.on('dblclick', e => moveRef.current && moveRef.current([e.latlng.lat, e.latlng.lng]))

    // Keep Leaflet's tile grid in sync with container size. Without this, any
    // layout change (fullscreen toggle, side-panel open, window resize) leaves
    // half the viewport blank or misaligned until the next pan.
    requestAnimationFrame(() => map.invalidateSize())
    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(elRef.current)
    const onWinResize = () => map.invalidateSize()
    window.addEventListener('resize', onWinResize)

    return () => {
      ro.disconnect()
      window.removeEventListener('resize', onWinResize)
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

  // Grey dots + fit/pan. Fit to all dots on data change; pan to a selected store.
  useEffect(() => {
    const map = mapRef.current, layer = storeLayerRef.current
    if (!map || !layer) return
    drawStores(L, layer, stores, { selectedId, onSelect: onSelectStore, onView: onViewStore })

    if (selectedId) {
      const sel = stores.find(s => s.id === selectedId)
      if (sel && sel.lat != null) map.panTo([sel.lat, sel.lng], { animate: true })
    } else if (!clusterCenter) {
      const pts = stores.filter(s => s.lat != null && s.lng != null).map(s => [s.lat, s.lng])
      if (pts.length) map.fitBounds(pts, { padding: [50, 50], maxZoom: 14 })
    }
  }, [stores, selectedId])

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

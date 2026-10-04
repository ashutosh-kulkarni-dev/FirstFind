import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import L from 'leaflet'
import StoreCard from '../components/StoreCard'
import { api } from '../api'

const ZONE_PALETTE = ['#c8f048', '#f4a988', '#9aa69c', '#ffc75f', '#a8d8ea', '#f7b7a3']
const zoneColor = (i) => ZONE_PALETTE[i % ZONE_PALETTE.length]

// Preset values reasoned for Bengaluru thrift use-case:
// 1.2 km = comfortable walk (~15 min), 2.5 km = quick scooter/cycle,
// 5 km = auto range (~15 min), 10 km = city-wide cab search
const RADIUS_PRESETS = [
  { label: 'Walk', value: 1.2 },
  { label: 'Scooter', value: 2.5 },
  { label: 'Auto', value: 5 },
  { label: 'Cab', value: 10 },
]

function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLng = (lng2 - lng1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

function storesInRadius(allStores, lat, lng, radiusKm) {
  return allStores.filter(s =>
    s.lat != null && s.lng != null && haversineKm(lat, lng, s.lat, s.lng) <= radiusKm
  )
}

function nearestStation(metroData, lat, lng) {
  if (!metroData) return null
  let best = null, bestDist = Infinity
  for (const line of metroData.lines) {
    for (const st of line.stations) {
      const d = haversineKm(lat, lng, st.lat, st.lng)
      if (d < bestDist) {
        bestDist = d
        best = { name: st.name, distanceM: Math.round(d * 1000), lineColor: line.color, lineId: line.id, lineName: line.name }
      }
    }
  }
  return best
}

function drawSubZoneLayers(map, subZones, layersArr) {
  layersArr.forEach(l => l.remove()); layersArr.length = 0
  subZones.forEach((sz, i) => {
    const color = zoneColor(i + 1)
    const circle = L.circle([sz.center_lat, sz.center_lng], {
      radius: (sz.radius_km || 1) * 1000, color, fillColor: color, fillOpacity: 0.12, weight: 2,
    }).addTo(map).bindPopup(`<b>${sz.label}</b><br/>${sz.store_count} stores`)
    layersArr.push(circle)
    sz.stores.forEach(s => {
      if (s.lat == null) return
      const pin = L.circleMarker([s.lat, s.lng], {
        radius: 5, color: '#0c0f0d', fillColor: color, fillOpacity: 0.9, weight: 1,
      }).addTo(map).bindPopup(`<b>${s.name}</b><br/>${s.area}`)
      layersArr.push(pin)
    })
  })
}

// Metro stop: line-colored hollow ring — visually distinct from solid store dots
const metroIcon = (color) => L.divIcon({
  className: 'metro-stop',
  html: `<div style="width:14px;height:14px;border-radius:50%;border:2.5px solid ${color};background:transparent;box-shadow:0 0 0 2px rgba(12,15,13,.9)"></div>`,
  iconSize: [14, 14], iconAnchor: [7, 7],
})

// Score → dot color, mirrors Explore page
function scoreColor(score) {
  if (score >= 4) return '#6fe3a5'
  if (score >= 3) return '#ffc75f'
  if (score) return '#ff6b6b'
  return '#9aa69c'
}

// Human-readable range label for the slider
function rangeLabel(km) {
  if (km <= 1.2) return '~15-min walk'
  if (km <= 3)   return '~5-min scooter · 10-min walk'
  if (km <= 6)   return '~15-min auto · 20-min cycle'
  return '~15-min cab'
}

export default function Zones() {
  const [searchParams] = useSearchParams()
  const [zones, setZones] = useState([])
  const [areaOptions, setAreaOptions] = useState([])
  const [allStores, setAllStores] = useState([])
  const [metroData, setMetroData] = useState(null)
  const mapRef = useRef(null)
  const mapObj = useRef(null)
  const zoneLayers = useRef([])
  const storeDotLayers = useRef([])
  const modeBLayers = useRef([])
  const subZoneLayers = useRef([])
  const metroLayers = useRef([])
  const dragMarker = useRef(null)
  const previewCircle = useRef(null)

  const [mode, setMode] = useState('A')
  const [selectedArea, setSelectedArea] = useState('')
  const [radiusKm, setRadiusKm] = useState(2.5)
  const [includeSolo, setIncludeSolo] = useState(false)
  const [showMetro, setShowMetro] = useState(true)   // metro on by default
  const [showZoneRings, setShowZoneRings] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [panelOpen, setPanelOpen] = useState(true)
  const [finding, setFinding] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [findResult, setFindResult] = useState(null)
  const [subZones, setSubZones] = useState(null)
  const centerRef = useRef(null)
  const enterModeBRef = useRef(null)  // always points to latest enterModeB

  // Phase 2 fix: refs that always hold the live values so drag closures never go stale
  const radiusRef = useRef(radiusKm)
  const includeSoloRef = useRef(includeSolo)
  useEffect(() => { radiusRef.current = radiusKm }, [radiusKm])
  useEffect(() => { includeSoloRef.current = includeSolo }, [includeSolo])

  useEffect(() => {
    api.zones().then(setZones).catch(() => {})
    api.areaCoords().then(setAreaOptions).catch(() => {})
    api.stores().then(r => setAllStores(r.stores || [])).catch(() => {})
    api.metroStations().then(setMetroData).catch(() => {})
  }, [])

  // ── Deep-link from chat "View on full map" button ─────────────────────────
  // When ?lat=&lng=&radius= are present (set by chat action), switch to Mode B
  // and trigger a cluster search at those coords. Runs once after map is ready.
  useEffect(() => {
    const lat = parseFloat(searchParams.get('lat'))
    const lng = parseFloat(searchParams.get('lng'))
    const radius = parseFloat(searchParams.get('radius'))
    if (!lat || !lng || !radius) return
    // Wait for the map and enterModeB ref to be available
    const attempt = () => {
      if (enterModeBRef.current && mapObj.current) {
        setMode('B')
        setRadiusKm(radius)
        mapObj.current.setView([lat, lng], 14)
        enterModeBRef.current(lat, lng)
      } else {
        setTimeout(attempt, 150)
      }
    }
    attempt()
  }, []) // intentionally runs once on mount

  // ── Map init ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (mapObj.current || !mapRef.current) return
    const map = L.map(mapRef.current, { doubleClickZoom: false }).setView([12.9716, 77.5946], 12)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
    }).addTo(map)
    // Double-click anywhere on the map to drop a cluster pin at that point
    map.on('dblclick', (e) => {
      enterModeBRef.current?.(e.latlng.lat, e.latlng.lng)
    })
    mapObj.current = map
    return () => { map.remove(); mapObj.current = null }
  }, [])

  // ── Fullscreen: invalidate map size after CSS transition, lock scroll ─────
  useEffect(() => {
    document.body.style.overflow = fullscreen ? 'hidden' : ''
    const t = setTimeout(() => mapObj.current?.invalidateSize(), 320)
    return () => clearTimeout(t)
  }, [fullscreen])

  // Escape key exits fullscreen
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape' && fullscreen) setFullscreen(false) }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [fullscreen])

  // ── Metro overlay ─────────────────────────────────────────────────────────
  useEffect(() => {
    const map = mapObj.current
    if (!map || !metroData) return
    metroLayers.current.forEach(l => l.remove())
    metroLayers.current = []
    if (!showMetro) return

    for (const line of metroData.lines) {
      const coords = [...line.stations].sort((a, b) => a.order - b.order).map(s => [s.lat, s.lng])
      const poly = L.polyline(coords, { color: line.color, weight: 3, opacity: 0.85 }).addTo(map)
      metroLayers.current.push(poly)

      for (const st of line.stations) {
        const isOperational = !st.phase || st.phase === 'operational'
        const icon = isOperational
          ? metroIcon(line.color)
          : metroIcon(line.color + '88')  // muted for under-construction
        const pin = L.marker([st.lat, st.lng], { icon }).addTo(map)
        pin.bindTooltip(`${st.name} — ${line.name}`, { permanent: false, direction: 'top', className: 'metro-tooltip' })
        metroLayers.current.push(pin)
      }
    }
  }, [showMetro, metroData])

  // ── Store dots (Mode A base layer — replaces overlapping zone circles) ────
  useEffect(() => {
    const map = mapObj.current
    storeDotLayers.current.forEach(l => l.remove()); storeDotLayers.current = []
    if (!map || !allStores.length || mode !== 'A') return
    if (showZoneRings) return  // rings are on, skip dots to avoid double-clutter

    allStores.forEach(s => {
      if (s.lat == null) return
      const dot = L.circleMarker([s.lat, s.lng], {
        radius: 5, color: '#0c0f0d', weight: 1,
        fillColor: scoreColor(s.experience_score), fillOpacity: 0.9,
      }).addTo(map).bindPopup(`<b>${s.name}</b><br/>${s.area}`)
      storeDotLayers.current.push(dot)
    })
  }, [allStores, mode, showZoneRings])

  // ── Zone rings (opt-in, off by default) ───────────────────────────────────
  useEffect(() => {
    const map = mapObj.current
    zoneLayers.current.forEach(l => l.remove()); zoneLayers.current = []
    if (!map || !zones.length || mode !== 'A' || !showZoneRings) return

    zones.forEach((z, i) => {
      const color = zoneColor(i)
      const circle = L.circle([z.center_lat, z.center_lng], {
        radius: (z.radius_km || 2.2) * 1000, color, fillColor: color, fillOpacity: 0.08,
        weight: 2, dashArray: '6 6',
      }).addTo(map).bindPopup(
        `<b>${z.label}</b><br/>${z.store_count} stores · ~${z.radius_km?.toFixed(1) ?? '?'} km`
        + (z.avg_score ? ` · avg ★${z.avg_score}` : '')
      )
      zoneLayers.current.push(circle)
    })
  }, [zones, mode, showZoneRings])

  // ── Live preview circle ───────────────────────────────────────────────────
  const updatePreview = useCallback((lat, lng, r) => {
    const map = mapObj.current; if (!map) return
    if (previewCircle.current) {
      previewCircle.current.setLatLng([lat, lng]).setRadius(r * 1000)
    } else {
      previewCircle.current = L.circle([lat, lng], {
        radius: r * 1000, color: '#c8f048', fillColor: '#c8f048',
        fillOpacity: 0.12, weight: 2, dashArray: '4 4', interactive: false,
      }).addTo(map)
    }
  }, [])

  useEffect(() => {
    if (mode !== 'B' || !centerRef.current) return
    updatePreview(centerRef.current.lat, centerRef.current.lng, radiusKm)
  }, [radiusKm, mode, updatePreview])

  // ── Commit find (reads from refs — not from closure) ─────────────────────
  // commitFind itself uses refs so the drag handler's cached reference stays valid
  const commitFind = useCallback((lat, lng) => {
    const currentRadius = radiusRef.current
    const currentIncludeSolo = includeSoloRef.current
    setFinding(true); setFindResult(null); setSubZones(null)
    subZoneLayers.current.forEach(l => l.remove()); subZoneLayers.current = []
    const minShops = currentIncludeSolo ? 1 : 3
    api.findCluster({ lat, lng, radius_km: currentRadius, min_shops: minShops, max_shops: 8 })
      .then(r => {
        setFindResult(r)
        const map = mapObj.current; if (!map || r.honest_empty) return
        modeBLayers.current.forEach(l => l.remove()); modeBLayers.current = []
        r.stores.forEach(s => {
          if (s.lat == null) return
          const pin = L.circleMarker([s.lat, s.lng], {
            radius: 6, color: '#0c0f0d', fillColor: '#c8f048', fillOpacity: 0.9, weight: 1,
          }).addTo(map).bindPopup(`<b>${s.name}</b><br/>${s.area}`)
          modeBLayers.current.push(pin)
        })
      })
      .catch(() => setFindResult(null))
      .finally(() => setFinding(false))
  }, []) // no state deps — reads from refs, never goes stale

  // ── Split ─────────────────────────────────────────────────────────────────
  const handleSplit = () => {
    if (!centerRef.current) return
    const { lat, lng } = centerRef.current
    setSplitting(true); setSubZones(null)
    api.splitCluster({ lat, lng, radius_km: radiusRef.current, max_shops: 8 })
      .then(r => {
        setSubZones(r.sub_zones)
        const map = mapObj.current; if (!map) return
        modeBLayers.current.forEach(l => l.remove()); modeBLayers.current = []
        drawSubZoneLayers(map, r.sub_zones, subZoneLayers.current)
      })
      .catch(() => setSubZones(null))
      .finally(() => setSplitting(false))
  }

  // ── Drag marker — Phase 2 fix: handlers read from radiusRef, never stale ──
  const placeDragMarker = useCallback((lat, lng) => {
    const map = mapObj.current; if (!map) return
    modeBLayers.current.forEach(l => l.remove()); modeBLayers.current = []
    subZoneLayers.current.forEach(l => l.remove()); subZoneLayers.current = []
    centerRef.current = { lat, lng }
    updatePreview(lat, lng, radiusRef.current)
    if (dragMarker.current) { dragMarker.current.setLatLng([lat, lng]); return }
    const marker = L.marker([lat, lng], { draggable: true, title: 'Drag to reposition' }).addTo(map)
    marker.on('drag', e => {
      const { lat: mlat, lng: mlng } = e.target.getLatLng()
      centerRef.current = { lat: mlat, lng: mlng }
      updatePreview(mlat, mlng, radiusRef.current)  // always reads live radius
    })
    marker.on('dragend', e => {
      const { lat: mlat, lng: mlng } = e.target.getLatLng()
      centerRef.current = { lat: mlat, lng: mlng }
      setSubZones(null); commitFind(mlat, mlng)  // commitFind also reads from refs
    })
    dragMarker.current = marker
  }, [updatePreview, commitFind])  // commitFind is stable (no state deps)

  const clearModeB = () => {
    ;[modeBLayers, subZoneLayers].forEach(r => { r.current.forEach(l => l.remove()); r.current = [] })
    if (previewCircle.current) { previewCircle.current.remove(); previewCircle.current = null }
    if (dragMarker.current) { dragMarker.current.remove(); dragMarker.current = null }
    centerRef.current = null
  }

  const enterModeB = (lat, lng) => {
    zoneLayers.current.forEach(l => l.remove()); zoneLayers.current = []
    storeDotLayers.current.forEach(l => l.remove()); storeDotLayers.current = []
    setMode('B'); setSubZones(null)
    placeDragMarker(lat, lng); commitFind(lat, lng)
    mapObj.current?.setView([lat, lng], 14)
  }
  enterModeBRef.current = enterModeB  // keep ref fresh every render (no extra effect needed)

  const handleFindByArea = () => {
    const opt = areaOptions.find(a => a.name === selectedArea); if (!opt) return
    enterModeB(opt.lat, opt.lng)
  }

  const useGPS = () => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(pos =>
      enterModeB(pos.coords.latitude, pos.coords.longitude)
    )
  }

  const handleRadiusCommit = () => {
    if (mode !== 'B' || !centerRef.current) return
    setSubZones(null); commitFind(centerRef.current.lat, centerRef.current.lng)
  }

  const switchToA = () => {
    setMode('A'); setFindResult(null); setSubZones(null)
    clearModeB()
    mapObj.current?.setView([12.9716, 77.5946], 12)
  }

  // Once a real result exists, use the server-confirmed count — never the client estimate
  const previewCount = mode === 'B' && centerRef.current && !findResult
    ? storesInRadius(allStores, centerRef.current.lat, centerRef.current.lng, radiusKm).length
    : findResult && !findResult.honest_empty
    ? findResult.stores.length
    : null

  const enrichWithMetro = (stores) => {
    if (!metroData || !showMetro) return stores
    return stores.map(s => {
      if (s.lat == null) return s
      const near = nearestStation(metroData, s.lat, s.lng)
      return near ? { ...s, _metro: near } : s
    })
  }

  const renderStores = (stores) =>
    enrichWithMetro(stores).map(s => (
      <div key={s.id}>
        <StoreCard store={s} compact />
        {s._metro && (
          <p style={{ fontSize: 11, color: s._metro.lineColor, marginTop: -6, marginBottom: 6, paddingLeft: 4 }}>
            ~{s._metro.distanceM} m from {s._metro.name}
          </p>
        )}
      </div>
    ))

  // ── Range Card + Controls JSX (plain variables, not inner components,
  //    to avoid remount-on-every-render from new function identity) ──────────
  const pct = `${((radiusKm - 0.5) / (10 - 0.5)) * 100}%`

  const rangeCardJsx = (
    <div className="range-card">
      <h3>How far are you willing to go?</h3>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <input
          type="range" min={0.5} max={10} step={0.5} value={radiusKm}
          className="range-track"
          style={{ '--pct': pct, flex: 1 }}
          onChange={e => setRadiusKm(Number(e.target.value))}
          onMouseUp={handleRadiusCommit} onTouchEnd={handleRadiusCommit}
        />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--accent)', minWidth: 56, textAlign: 'right' }}>
          {radiusKm} km
          {previewCount !== null && <span style={{ color: 'var(--text-dim)', fontWeight: 400, fontSize: 12 }}> · {previewCount}</span>}
        </span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 12 }}>{rangeLabel(radiusKm)}</div>
      <div className="range-presets">
        {RADIUS_PRESETS.map(p => (
          <button
            key={p.value}
            className={`range-pill${radiusKm === p.value ? ' active' : ''}`}
            onClick={() => { setRadiusKm(p.value); radiusRef.current = p.value; handleRadiusCommit() }}
          >{p.label} {p.value} km</button>
        ))}
      </div>
    </div>
  )

  const controlsJsx = (
    <>
      {rangeCardJsx}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 12, alignItems: 'center' }}>
        <select value={selectedArea} onChange={e => setSelectedArea(e.target.value)}
          style={{ padding: '6px 10px', borderRadius: 8, background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)', minWidth: 160 }}>
          <option value="">Pick an area…</option>
          {areaOptions.filter(a => a.kind === 'area').map(a => (
            <option key={a.name} value={a.name}>{a.name} ({a.count})</option>
          ))}
          <optgroup label="Sub-localities">
            {areaOptions.filter(a => a.kind === 'locality').map(a => (
              <option key={a.name} value={a.name}>{a.name} ({a.count})</option>
            ))}
          </optgroup>
        </select>

        <button onClick={handleFindByArea} disabled={!selectedArea || finding}
          style={{ padding: '6px 14px', borderRadius: 8, background: 'var(--accent)', color: '#000', border: 'none', cursor: 'pointer', fontWeight: 600 }}>
          {finding ? 'Finding…' : 'Find'}
        </button>
        <button onClick={useGPS}
          style={{ padding: '6px 12px', borderRadius: 8, background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)', cursor: 'pointer' }}>
          📍 My location
        </button>
        {mode === 'B' && (
          <button onClick={switchToA}
            style={{ padding: '6px 12px', borderRadius: 8, background: 'transparent', color: 'var(--text-dim)', border: '1px solid var(--border)', cursor: 'pointer', fontSize: 13 }}>
            ← All zones
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: showMetro ? '#c8f048' : 'var(--text-dim)' }}>
          <input type="checkbox" checked={showMetro} onChange={e => setShowMetro(e.target.checked)} />
          🚇 Metro lines
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: 'var(--text-dim)' }}>
          <input type="checkbox" checked={includeSolo} onChange={e => setIncludeSolo(e.target.checked)} />
          Include solo shops
        </label>
        {mode === 'A' && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer', color: 'var(--text-dim)' }}>
            <input type="checkbox" checked={showZoneRings} onChange={e => setShowZoneRings(e.target.checked)} />
            Show zone rings
          </label>
        )}
      </div>
    </>
  )

  return (
    <div style={{ paddingTop: 100 }} className="container">
      <h1 className="section-title">Thrift Zones</h1>
      <p className="section-sub">
        Density-based clustering groups Bengaluru's thrift scene into geographic neighbourhoods.
        Use <b>Find</b> to explore any spot — or drag the pin on the map.
      </p>

      {/* Normal-mode controls (hidden when fullscreen — side panel takes over) */}
      {!fullscreen && controlsJsx}

      {/* Map container */}
      <div className={`map-wrap${fullscreen ? ' fullscreen' : ''}`} style={{ marginBottom: fullscreen ? 0 : 32 }}>
        <div ref={mapRef} style={{ height: '100%', borderRadius: 'inherit' }} />

        {/* Fullscreen toggle button */}
        <button
          className="map-fs-btn"
          onClick={() => setFullscreen(f => !f)}
          title={fullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen map'}
          style={{
            position: 'absolute', bottom: 16, right: 16, zIndex: 950,
            width: 36, height: 36, borderRadius: 8,
            background: 'rgba(20,26,20,.85)', border: '1px solid var(--border)',
            color: 'var(--text)', fontSize: 16, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            backdropFilter: 'blur(8px)',
          }}
        >{fullscreen ? '✕' : '⛶'}</button>

        {/* Fullscreen side panel */}
        {fullscreen && (
          <div className={`map-side-panel${panelOpen ? '' : ' collapsed'}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 15 }}>Thrift Zones</span>
              <button onClick={() => setPanelOpen(o => !o)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-dim)', fontSize: 18, cursor: 'pointer', lineHeight: 1 }}>
                {panelOpen ? '‹' : '›'}
              </button>
            </div>
            {controlsJsx}
          </div>
        )}

        {/* Panel collapsed tab — chevron peeking out */}
        {fullscreen && !panelOpen && (
          <button onClick={() => setPanelOpen(true)}
            style={{
              position: 'absolute', top: '50%', left: 0, transform: 'translateY(-50%)',
              zIndex: 960, background: 'rgba(20,26,20,.85)', border: '1px solid var(--border)',
              borderLeft: 'none', borderRadius: '0 8px 8px 0', padding: '12px 6px',
              color: 'var(--text-dim)', cursor: 'pointer', backdropFilter: 'blur(8px)',
            }}>›</button>
        )}
      </div>

      {/* Mode B: find result */}
      {mode === 'B' && findResult && !finding && !subZones && (
        <div style={{ marginBottom: 32 }}>
          {findResult.honest_empty ? (
            <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-dim)' }}>
              <p style={{ fontSize: 18, marginBottom: 12 }}>No stores found within {radiusKm} km.</p>
              <p style={{ fontSize: 14, marginBottom: 16 }}>Try widening the radius or dragging the pin.</p>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                {[Math.round(radiusKm * 1.5 * 2) / 2, Math.round(radiusKm * 2 * 2) / 2].map(r => (
                  <button key={r}
                    onClick={() => { setRadiusKm(r); radiusRef.current = r; if (centerRef.current) commitFind(centerRef.current.lat, centerRef.current.lng) }}
                    style={{ padding: '6px 14px', borderRadius: 8, background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)', cursor: 'pointer' }}>
                    Try {r} km
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
                <h2 style={{ margin: 0 }}>{findResult.label}</h2>
                <span style={{ color: 'var(--text-dim)', fontSize: 14 }}>
                  {findResult.store_count} store{findResult.store_count !== 1 ? 's' : ''} within {radiusKm} km
                  {findResult.avg_score ? ` · avg ★${findResult.avg_score}` : ''}
                  {findResult.avg_price ? ` · avg ₹${Math.round(findResult.avg_price)}` : ''}
                </span>
                {findResult.over_cap && (
                  <button onClick={handleSplit} disabled={splitting}
                    style={{ padding: '4px 12px', borderRadius: 6, fontSize: 13, cursor: 'pointer', background: 'rgba(255,199,95,0.15)', color: '#ffc75f', border: '1px solid #ffc75f' }}>
                    {splitting ? 'Splitting…' : 'Too many stores — tap to split'}
                  </button>
                )}
              </div>
              <div className="grid grid-3">{renderStores(findResult.stores)}</div>
            </>
          )}
        </div>
      )}

      {/* Sub-zones */}
      {mode === 'B' && subZones && (
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            <h2 style={{ margin: 0 }}>Sub-zones ({subZones.length})</h2>
            <button
              onClick={() => {
                setSubZones(null)
                subZoneLayers.current.forEach(l => l.remove()); subZoneLayers.current = []
                modeBLayers.current.forEach(l => l.remove()); modeBLayers.current = []
                if (findResult) {
                  const map = mapObj.current
                  if (map) findResult.stores.forEach(s => {
                    if (s.lat == null) return
                    const pin = L.circleMarker([s.lat, s.lng], { radius: 6, color: '#0c0f0d', fillColor: '#c8f048', fillOpacity: 0.9, weight: 1 }).addTo(map)
                    pin.bindPopup(`<b>${s.name}</b><br/>${s.area}`)
                    modeBLayers.current.push(pin)
                  })
                }
              }}
              style={{ fontSize: 13, color: 'var(--text-dim)', background: 'transparent', border: '1px solid var(--border)', borderRadius: 6, padding: '3px 10px', cursor: 'pointer' }}>
              ← Back to full result
            </button>
          </div>
          <div className="grid grid-3" style={{ paddingBottom: 24 }}>
            {subZones.map((sz, i) => (
              <div key={i} className="card zone-card" style={{ borderTop: `3px solid ${zoneColor(i + 1)}` }}>
                <h3>{sz.label}</h3>
                <div className="zone-stats">
                  <div className="zs"><div className="v">{sz.store_count}</div><div className="l">stores</div></div>
                  <div className="zs"><div className="v">~{sz.radius_km?.toFixed(1)} km</div><div className="l">radius</div></div>
                  <div className="zs"><div className="v">★{sz.avg_score ?? '—'}</div><div className="l">avg score</div></div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 10 }}>
                  {renderStores(sz.stores)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Mode A: precomputed zones grid */}
      {mode === 'A' && (
        <div className="grid grid-3" style={{ paddingBottom: 80 }}>
          {zones.map((z, i) => (
            <div key={z.id} className="card zone-card" style={{ borderTop: `3px solid ${zoneColor(i)}` }}>
              <h3>{z.label}</h3>
              <div className="zone-stats">
                <div className="zs"><div className="v">{z.store_count}</div><div className="l">stores</div></div>
                <div className="zs"><div className="v">★{z.avg_score ?? '—'}</div><div className="l">avg score</div></div>
                <div className="zs"><div className="v">~{z.radius_km?.toFixed(1) ?? '?'} km</div><div className="l">radius</div></div>
              </div>
              {z.avg_price ? (
                <p style={{ color: 'var(--text-dim)', fontSize: 13, marginBottom: 10 }}>avg price ₹{Math.round(z.avg_price)}</p>
              ) : null}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(z.top_stores || []).map(s => <StoreCard key={s.id} store={s} compact />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

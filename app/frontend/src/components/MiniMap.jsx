// MiniMap — read-only Leaflet map for chat context bubbles. FIRSTFIND palette.
import { useEffect, useRef } from 'react'
import L from 'leaflet'

const TILE_URL = import.meta.env.VITE_MAP_TILE_URL
  || 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'

function dotColor(isOpen) {
  if (isOpen === true) return '#22c55e'
  if (isOpen === false) return '#f43f5e'
  return '#94a3b8'
}

const metroIcon = (color) => L.divIcon({
  className: '',
  html: `<div style="width:12px;height:12px;border-radius:50%;border:2.5px solid ${color};background:transparent;box-shadow:0 0 0 2px rgba(15,26,43,.9)"></div>`,
  iconSize: [12, 12], iconAnchor: [6, 6],
})

export default function MiniMap({ center, radiusKm, stores = [], metro = null }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !center) return
    if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }

    const map = L.map(containerRef.current, {
      center, zoom: 14, zoomControl: false, dragging: false, scrollWheelZoom: false,
      doubleClickZoom: false, boxZoom: false, keyboard: false, attributionControl: false,
    })
    L.tileLayer(TILE_URL, { maxZoom: 19 }).addTo(map)
    // Defer invalidateSize to next frame so the container has a real size
    // (chat bubbles mount with height:0 for one tick on first render).
    requestAnimationFrame(() => map.invalidateSize())

    if (radiusKm) {
      L.circle(center, { radius: radiusKm * 1000, color: '#33a0e6', fillColor: '#33a0e6', fillOpacity: 0.12, weight: 1.5 }).addTo(map)
    }
    stores.forEach(s => {
      if (s.lat == null || s.lng == null) return
      L.circleMarker([s.lat, s.lng], { radius: 6, color: '#0f1a2b', fillColor: dotColor(s.is_open_now), fillOpacity: 0.95, weight: 1 })
        .addTo(map).bindPopup(`<b>${s.name}</b>`)
    })
    if (metro && metro.lat != null) {
      L.marker([metro.lat, metro.lng], { icon: metroIcon(metro.line_color || '#888') })
        .addTo(map).bindPopup(`${metro.name} — ${metro.line_name}<br/>${metro.distance_m} m away`)
    }

    mapRef.current = map
    return () => { map.remove(); mapRef.current = null }
  }, [center?.[0], center?.[1], radiusKm, stores.length])

  if (!center) return null
  return <div ref={containerRef} style={{ width: '100%', height: 180, borderRadius: 12, overflow: 'hidden', marginTop: 10, border: '1px solid var(--line)', pointerEvents: 'none' }} />
}

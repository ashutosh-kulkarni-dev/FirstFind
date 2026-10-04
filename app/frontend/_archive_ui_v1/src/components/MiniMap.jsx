/**
 * MiniMap — read-only Leaflet map for chat context.
 *
 * Props:
 *   center    [lat, lng]
 *   radiusKm  number
 *   stores    [{id, name, lat, lng, is_open_now}]
 *   metro     {name, line_name, line_color, distance_m} | null
 *
 * Shared by ChatCore (inline in chat bubble) and optionally Zones (thumbnail).
 * Never receives interactive controls — those belong to the Zones page.
 */
import { useEffect, useRef } from 'react'
import L from 'leaflet'

function scoreColor(isOpen) {
  if (isOpen === true) return '#6fe3a5'
  if (isOpen === false) return '#ff6b6b'
  return '#9aa69c'
}

const metroIcon = (color) => L.divIcon({
  className: '',
  html: `<div style="width:12px;height:12px;border-radius:50%;border:2.5px solid ${color};background:transparent;box-shadow:0 0 0 2px rgba(12,15,13,.9)"></div>`,
  iconSize: [12, 12], iconAnchor: [6, 6],
})

export default function MiniMap({ center, radiusKm, stores = [], metro = null }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !center) return

    // Destroy any previous instance (hot-reload safety)
    if (mapRef.current) {
      mapRef.current.remove()
      mapRef.current = null
    }

    const map = L.map(containerRef.current, {
      center,
      zoom: 14,
      zoomControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      attributionControl: false,
    })

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
    }).addTo(map)

    // Radius circle
    if (radiusKm) {
      L.circle(center, {
        radius: radiusKm * 1000,
        color: '#c8f048',
        fillColor: '#c8f048',
        fillOpacity: 0.08,
        weight: 1.5,
      }).addTo(map)
    }

    // Store dots
    stores.forEach(s => {
      if (s.lat == null || s.lng == null) return
      L.circleMarker([s.lat, s.lng], {
        radius: 6,
        color: '#0c0f0d',
        fillColor: scoreColor(s.is_open_now),
        fillOpacity: 0.9,
        weight: 1,
      }).addTo(map).bindPopup(`<b>${s.name}</b>`)
    })

    // Metro station
    if (metro && metro.lat != null) {
      L.marker([metro.lat, metro.lng], { icon: metroIcon(metro.line_color || '#888') })
        .addTo(map)
        .bindPopup(`${metro.name} — ${metro.line_name}<br/>${metro.distance_m} m away`)
    }

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [center?.[0], center?.[1], radiusKm, stores.length])

  if (!center) return null

  return (
    <div
      ref={containerRef}
      style={{
        height: 180,
        borderRadius: 12,
        overflow: 'hidden',
        marginTop: 10,
        border: '1px solid #2a3a2a',
        pointerEvents: 'none',
      }}
    />
  )
}

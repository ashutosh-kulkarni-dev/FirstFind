// A small map with one draggable pin. Click the map to place the pin when the
// store has none; drag it to move. Reports the new position through onChange.
import { useEffect, useRef } from 'react'
import L from 'leaflet'
import { createDarkMap } from '../../lib/map/leaflet'

const BLR = [12.9716, 77.5946]

const pinIcon = L.divIcon({
  className: '',
  html: '<div class="admin-pin"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 22],
})

export default function PinMap({ lat, lng, onChange }) {
  const elRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const changeRef = useRef(onChange)
  useEffect(() => { changeRef.current = onChange }, [onChange])

  useEffect(() => {
    const map = createDarkMap(elRef.current)
    mapRef.current = map
    map.on('click', e => {
      if (!markerRef.current) changeRef.current(round(e.latlng.lat), round(e.latlng.lng))
    })
    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(elRef.current)
    return () => { ro.disconnect(); map.remove(); mapRef.current = null; markerRef.current = null }
  }, [])

  // Keep the marker in step with the form (typing coordinates also moves it).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const has = lat != null && lng != null && !Number.isNaN(lat) && !Number.isNaN(lng)
    if (!has) {
      if (markerRef.current) { markerRef.current.remove(); markerRef.current = null }
      map.setView(BLR, 11)
      return
    }
    if (!markerRef.current) {
      const m = L.marker([lat, lng], { draggable: true, icon: pinIcon, autoPan: true }).addTo(map)
      m.on('dragend', () => {
        const p = m.getLatLng()
        changeRef.current(round(p.lat), round(p.lng))
      })
      markerRef.current = m
      map.setView([lat, lng], 16)
    } else {
      const cur = markerRef.current.getLatLng()
      if (cur.lat !== lat || cur.lng !== lng) {
        markerRef.current.setLatLng([lat, lng])
        if (!map.getBounds().contains([lat, lng])) map.panTo([lat, lng])
      }
    }
  }, [lat, lng])

  return <div ref={elRef} className="admin-pinmap" aria-label="Store location map" />
}

const round = (v) => Math.round(v * 1e6) / 1e6

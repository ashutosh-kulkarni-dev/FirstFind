import { storePopupHtml } from './leaflet'
import { scoreHex } from '../score'

// Store markers coloured by AI experience score (matches the Explore mockup +
// sidebar legend). Open stores get a pulsing ring; the selected one is larger
// and outlined. Clicking selects; the popup's "View store" link routes via onView.
export function drawStores(L, layer, stores, { selectedId, onSelect, onView }) {
  layer.clearLayers()
  stores.forEach(store => {
    if (store.lat == null || store.lng == null) return
    const selected = store.id === selectedId
    const c = scoreHex(store.score)
    const size = selected ? 16 : 12
    const label = store.score != null ? Number(store.score).toFixed(1) : ''
    const ping = store.open
      ? `<span style="position:absolute;left:50%;top:50%;width:${size}px;height:${size}px;margin:${-size / 2}px 0 0 ${-size / 2}px;border-radius:50%;background:${c};opacity:.5;animation:ffPing 1.8s ease-out infinite;"></span>`
      : ''
    const icon = L.divIcon({
      className: '',
      html: `<div style="position:relative;">
        ${ping}
        <span style="position:relative;display:grid;place-items:center;width:${size}px;height:${size}px;border-radius:50%;background:${c};border:${selected ? 3 : 2}px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.45);font:700 9px Inter,sans-serif;color:#0f1a2b;">${label}</span>
      </div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    })
    const marker = L.marker([store.lat, store.lng], { icon, zIndexOffset: selected ? 1000 : 0 })
    marker.on('click', () => onSelect && onSelect(store.id))
    marker.bindPopup(storePopupHtml(store))
    marker.on('popupopen', ev => {
      const a = ev.popup.getElement()?.querySelector('a[data-store-id]')
      if (a) {
        a.addEventListener('click', e => {
          e.preventDefault()
          onView && onView(store.id)
        })
      }
    })
    layer.addLayer(marker)
  })
}

// The movable cluster: a dashed radius ring plus a draggable centre pin.
// Dragging updates the ring live and commits the new centre on drop.
export function drawCluster(L, layer, { center, radiusKm, onDragEnd }) {
  layer.clearLayers()

  const ring = L.circle(center, {
    radius: radiusKm * 1000,
    color: '#84cc16',
    fillColor: '#84cc16',
    fillOpacity: 0.08,
    weight: 2,
    dashArray: '6 4',
  })

  const pin = L.marker(center, {
    draggable: true,
    icon: L.divIcon({
      className: '',
      html: `<div style="width:20px;height:20px;border-radius:50%;background:#84cc16;border:2.5px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.45);"></div>`,
      iconSize: [20, 20],
      iconAnchor: [10, 10],
    }),
  })

  pin.on('drag', e => ring.setLatLng(e.latlng))
  pin.on('dragend', e => {
    const { lat, lng } = e.target.getLatLng()
    onDragEnd && onDragEnd([lat, lng])
  })

  layer.addLayer(ring)
  layer.addLayer(pin)
}

export function drawMetro(L, layer, metroLines) {
  layer.clearLayers()
  ;(metroLines ?? []).forEach(line => {
    const coords = (line.stations ?? []).map(s => [s.lat, s.lng])
    if (coords.length > 1) {
      L.polyline(coords, {
        color: line.color ?? '#888',
        weight: 2.5,
        opacity: 0.7,
      }).addTo(layer)
    }
    ;(line.stations ?? []).forEach(station => {
      L.circleMarker([station.lat, station.lng], {
        radius: 4,
        color: '#fff',
        fillColor: line.color ?? '#888',
        fillOpacity: 1,
        weight: 1.5,
      })
        .bindTooltip(station.name, { direction: 'top', sticky: true, className: 'metro-tip', opacity: 1 })
        .addTo(layer)
    })
  })
}


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

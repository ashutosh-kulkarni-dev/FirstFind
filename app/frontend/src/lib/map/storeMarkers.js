// Store markers for the Explore map, drawn on a canvas.
//
// The old version made one HTML element per store (545 of them, each with a
// CSS pulse animation) and rebuilt all of them on every click. Here:
//   * stores are dots on one <canvas>, so 500 stores cost one element;
//   * zoomed out, nearby stores are grouped into numbered clusters
//     (supercluster), redrawn only when the map stops moving;
//   * the selected and hovered stores are two extra, non-interactive dots drawn
//     over their store, so changing either redraws a few pixels, not the map.
// Everything shares one canvas: a second full-size canvas on top would swallow
// every mouse event meant for the dots underneath.
import Supercluster from 'supercluster'
import { scoreHex } from '../score'
import { storePopupHtml } from './leaflet'

const CLUSTER_MAX_ZOOM = 14      // from zoom 15 every store is drawn on its own
const CLUSTER_RADIUS_PX = 48
const SAME_SPOT_SPREAD = 0.00012 // ~13 m: stores sharing one pin are fanned out

// Several stores often share one pin (an area centroid). Fan them out in a small
// ring so each stays clickable; the stored coordinates are not changed.
function displayPositions(stores) {
  const groups = new Map()
  for (const s of stores) {
    if (s.lat == null || s.lng == null) continue
    const key = `${s.lat},${s.lng}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(s)
  }
  const pos = new Map()
  for (const group of groups.values()) {
    if (group.length === 1) { pos.set(group[0].id, [group[0].lat, group[0].lng]); continue }
    group.forEach((s, i) => {
      const a = (2 * Math.PI * i) / group.length
      const r = SAME_SPOT_SPREAD * (1 + Math.floor(i / 8) * 0.6)
      pos.set(s.id, [s.lat + r * Math.sin(a), s.lng + (r * Math.cos(a)) / Math.cos((s.lat * Math.PI) / 180)])
    })
  }
  return pos
}

function clusterIcon(L, count) {
  const size = count < 10 ? 30 : count < 50 ? 36 : count < 150 ? 42 : 48
  return L.divIcon({
    className: '',
    html: `<div class="ff-cluster" style="width:${size}px;height:${size}px">${count}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

export class StoreMarkers {
  constructor(L, map, { onSelect, onView, onHover }) {
    this.L = L
    this.map = map
    this.handlers = { onSelect, onView, onHover }
    this.byId = new Map()
    this.pos = new Map()
    this.index = null
    this.selectedId = null
    this.hoveredId = null
    this.popupFor = null

    this.rendered = new Set()    // ids drawn as single dots right now (not in a cluster)
    this.renderer = L.canvas({ padding: 0.3, tolerance: 4 })
    this.dots = L.layerGroup().addTo(map)
    this.clusters = L.layerGroup().addTo(map)
    this.highlight = L.layerGroup().addTo(map)

    this._onMove = () => this.render()
    map.on('moveend', this._onMove)
  }

  setHandlers(handlers) { this.handlers = handlers }

  setStores(stores) {
    this.byId = new Map(stores.map(s => [s.id, s]))
    this.pos = displayPositions(stores)
    const points = []
    for (const s of stores) {
      const p = this.pos.get(s.id)
      if (!p) continue
      points.push({ type: 'Feature', properties: { id: s.id }, geometry: { type: 'Point', coordinates: [p[1], p[0]] } })
    }
    this.index = new Supercluster({ radius: CLUSTER_RADIUS_PX, maxZoom: CLUSTER_MAX_ZOOM, minPoints: 3 })
    this.index.load(points)
    if (this.selectedId && !this.byId.has(this.selectedId)) this.selectedId = null
    if (this.hoveredId && !this.byId.has(this.hoveredId)) this.hoveredId = null
    this.render()
  }

  // Positions of the stores currently on the map (used to fit the view).
  bounds() {
    return [...this.pos.values()]
  }

  render() {
    const { L, map } = this
    this.dots.clearLayers()
    this.clusters.clearLayers()
    this.rendered = new Set()
    if (!this.index) return
    const b = map.getBounds().pad(0.25)
    const zoom = Math.round(map.getZoom())
    const features = this.index.getClusters([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], zoom)
    for (const f of features) {
      const [lng, lat] = f.geometry.coordinates
      if (f.properties.cluster) {
        const m = L.marker([lat, lng], { icon: clusterIcon(L, f.properties.point_count), keyboard: false })
        const id = f.properties.cluster_id
        m.on('click', () => {
          const z = Math.min(this.index.getClusterExpansionZoom(id), CLUSTER_MAX_ZOOM + 1)
          map.flyTo([lat, lng], z, { duration: 0.4 })
        })
        this.clusters.addLayer(m)
      } else {
        const store = this.byId.get(f.properties.id)
        if (store) { this.dots.addLayer(this._dot(store, [lat, lng])); this.rendered.add(store.id) }
      }
    }
    // Dots were redrawn underneath: put the highlight back on top.
    this._drawHighlight(false)
  }

  // Where a store is drawn, and whether it is inside a cluster at this zoom.
  position(id) { return this.pos.get(id) || null }
  isClustered(id) { return this.pos.has(id) && !this.rendered.has(id) }

  _dot(store, latlng) {
    const dot = this.L.circleMarker(latlng, {
      renderer: this.renderer,
      radius: 6,
      fillColor: scoreHex(store.score),
      fillOpacity: store.open === false ? 0.55 : 0.95,
      color: '#ffffff',
      weight: store.open ? 2 : 1,
      opacity: store.open ? 1 : 0.7,
    })
    this._wire(dot, store)
    return dot
  }

  _wire(layer, store) {
    layer.on('click', () => {
      this.popupFor = store.id
      this.handlers.onSelect?.(store.id)
    })
    layer.on('mouseover', () => this.handlers.onHover?.(store.id))
    layer.on('mouseout', () => this.handlers.onHover?.(null))
  }

  setHighlight(selectedId, hoveredId) {
    if (selectedId === this.selectedId && hoveredId === this.hoveredId) return
    this.selectedId = selectedId
    this.hoveredId = hoveredId
    this._drawHighlight()
  }

  _drawHighlight(withPopup = true) {
    const { L } = this
    this.highlight.clearLayers()
    const hovered = this.hoveredId && this.hoveredId !== this.selectedId ? this.byId.get(this.hoveredId) : null
    const selected = this.selectedId ? this.byId.get(this.selectedId) : null
    if (hovered && this.pos.has(hovered.id)) {
      const m = L.circleMarker(this.pos.get(hovered.id), {
        renderer: this.renderer, interactive: false, radius: 9,
        fillColor: scoreHex(hovered.score), fillOpacity: 1, color: '#33a0e6', weight: 3,
      })
      m.bindTooltip(hovered.name, { direction: 'top', offset: [0, -8] })
      this.highlight.addLayer(m)
      m.openTooltip()
    }
    if (selected && this.pos.has(selected.id)) {
      const m = L.circleMarker(this.pos.get(selected.id), {
        renderer: this.renderer, interactive: false, radius: 10,
        fillColor: scoreHex(selected.score), fillOpacity: 1, color: '#ffffff', weight: 3,
      })
      this.highlight.addLayer(m)
      if (withPopup && this.popupFor === selected.id) this._openPopup(selected)
    }
    if (withPopup) {
      if (!selected) this.map.closePopup()
      this.popupFor = null
    }
  }

  _openPopup(store) {
    const popup = this.L.popup({ offset: [0, -6] })
      .setLatLng(this.pos.get(store.id))
      .setContent(storePopupHtml(store))
      .openOn(this.map)
    const a = popup.getElement()?.querySelector('a[data-store-id]')
    if (a) {
      a.addEventListener('click', e => {
        e.preventDefault()
        this.handlers.onView?.(store.id)
      })
    }
  }

  destroy() {
    this.map.off('moveend', this._onMove)
    this.dots.remove(); this.clusters.remove(); this.highlight.remove()
  }
}

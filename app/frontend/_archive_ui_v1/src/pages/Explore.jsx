import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import L from 'leaflet'
import StoreCard from '../components/StoreCard'
import { api } from '../api'

const BLR = [12.9716, 77.5946]

function pinColor(score) {
  if (score == null) return '#9aa69c'
  if (score >= 4.0) return '#6fe3a5'
  if (score >= 3.0) return '#ffc75f'
  return '#ff6b6b'
}

export default function Explore() {
  const [stores, setStores] = useState([])
  const [areas, setAreas] = useState([])
  const [categories, setCategories] = useState([])
  const [filters, setFilters] = useState({ area: '', category: '', open_now: false, q: '' })
  const mapRef = useRef(null)
  const mapObj = useRef(null)
  const markersRef = useRef([])
  const nav = useNavigate()

  useEffect(() => { api.areas().then(setAreas).catch(() => {}) }, [])
  useEffect(() => { api.categories().then(setCategories).catch(() => {}) }, [])

  useEffect(() => {
    const params = { ...filters, open_now: filters.open_now ? 'true' : '' }
    api.stores(params).then(r => setStores(r.stores)).catch(() => {})
  }, [filters])

  // init map once
  useEffect(() => {
    if (mapObj.current || !mapRef.current) return
    const map = L.map(mapRef.current, { zoomControl: true }).setView(BLR, 12)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 19,
    }).addTo(map)
    mapObj.current = map
    return () => { map.remove(); mapObj.current = null }
  }, [])

  // sync markers
  useEffect(() => {
    const map = mapObj.current
    if (!map) return
    markersRef.current.forEach(m => m.remove())
    markersRef.current = stores.filter(s => s.lat).map(s => {
      const marker = L.circleMarker([s.lat, s.lng], {
        radius: 9, weight: 2, color: pinColor(s.experience_score),
        fillColor: pinColor(s.experience_score), fillOpacity: 0.45,
      }).addTo(map)
      marker.bindPopup(
        `<b>${s.name}</b><br/>${s.area}` +
        (s.experience_score ? `<br/>★ ${s.experience_score.toFixed(1)} (${s.review_count} reviews)` : '') +
        `<br/><a href="/store/${s.id}" data-id="${s.id}" style="color:#c8f048">View store →</a>`
      )
      marker.on('popupopen', (e) => {
        const link = e.popup.getElement().querySelector('a[data-id]')
        if (link) link.onclick = (ev) => { ev.preventDefault(); nav(`/store/${s.id}`) }
      })
      return marker
    })
  }, [stores, nav])

  const set = (k) => (e) =>
    setFilters(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const legend = useMemo(() => [
    ['#6fe3a5', '≥ 4.0'], ['#ffc75f', '3.0–3.9'], ['#ff6b6b', '< 3.0'], ['#9aa69c', 'unrated'],
  ], [])

  return (
    <div className="explore">
      <aside className="explore-side">
        <h2 style={{ marginBottom: 16 }}>Explore stores</h2>
        <div className="filters">
          <input type="text" placeholder="Search by name…" value={filters.q} onChange={set('q')} />
          <select value={filters.area} onChange={set('area')}>
            <option value="">All areas</option>
            {areas.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
          <select value={filters.category} onChange={set('category')}>
            <option value="">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <label><input type="checkbox" checked={filters.open_now} onChange={set('open_now')} /> Open now</label>
        </div>
        <div className="result-count">
          {stores.length} stores ·{' '}
          {legend.map(([c, l]) => (
            <span key={l} style={{ marginRight: 10 }}>
              <span className="open-dot" style={{ background: c }} />{l}
            </span>
          ))}
        </div>
        {stores.map(s => <StoreCard key={s.id} store={s} />)}
      </aside>
      <div className="explore-map"><div ref={mapRef} style={{ height: '100%' }} /></div>
    </div>
  )
}

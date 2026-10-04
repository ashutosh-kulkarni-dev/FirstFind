// Labels show diameter; km is the internal radius passed to the map.
export const RADIUS_PRESETS = [
  { label: '600 m', km: 0.3 },
  { label: '1.5 km', km: 0.75 },
  { label: '3 km', km: 1.5 },
  { label: '7 km', km: 3.5 },
]

// Read the Explore deep-link query (?lat&lng&radius) into a normalized shape.
// Callers ("Open on map" in Lists, the chat open_zones action) rely on this to
// land the user on the right cluster centre/radius. Returns nulls for absent
// params so the page can apply its own defaults — this helper owns parsing.
export function parseZoneParams(searchParams) {
  const lat = parseFloat(searchParams.get('lat'))
  const lng = parseFloat(searchParams.get('lng'))
  const radius = parseFloat(searchParams.get('radius'))
  const hasCenter = Number.isFinite(lat) && Number.isFinite(lng)
  return {
    hasCenter,
    center: hasCenter ? [lat, lng] : null,
    radiusKm: Number.isFinite(radius) ? radius : null,
  }
}

export function normalizeStore(store) {
  if (!store) return null
  // `categories` comes back as either a comma string or an array depending on
  // the endpoint — handle both so `cat` is a real label, not a stray character.
  const cats = Array.isArray(store.categories)
    ? store.categories
    : String(store.categories ?? '').split(',').map(s => s.trim()).filter(Boolean)
  return {
    id: store.id ?? null,
    name: store.name ?? '—',
    area: store.area ?? '',
    lat: store.lat ?? null,
    lng: store.lng ?? null,
    cat: cats[0] ?? '',
    score: store.experience_score ?? null,   // drives marker colour + legend (mockup)
    open: store.is_open_now ?? null,          // drives "Open now" filter + pulse
    distKm: store.distance_km ?? null,
  }
}

// Walking speed: 600 m / 10 min = 60 m/min. Above 1.5 km diameter → scooter.
export function reachLabel(radiusKm) {
  if (radiusKm == null) return '—'
  const d = radiusKm * 2
  if (d <= 1.5) {
    const mins = Math.round(d * 1000 / 60)
    return `~${mins} min walk`
  }
  return 'Scooter'
}

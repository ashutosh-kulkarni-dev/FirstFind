// Client-side radius clustering for the Explore map.
//
// The cluster honours the active sidebar filters: it is computed from the
// already-filtered store list the page holds, not a separate backend query.
// That keeps a single source of truth (the filtered stores) driving both the
// grey dots and the cluster panel.

const EARTH_KM = 6371

export function haversineKm(aLat, aLng, bLat, bLng) {
  const toRad = d => (d * Math.PI) / 180
  const dLat = toRad(bLat - aLat)
  const dLng = toRad(bLng - aLng)
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_KM * Math.asin(Math.sqrt(s))
}

// Return the stores within `radiusKm` of `center` ([lat, lng]), each annotated
// with its distance and sorted nearest-first. Stores without coordinates are
// skipped. Returns [] when there is no center.
export function storesWithinRadius(stores, center, radiusKm) {
  if (!center) return []
  const [lat, lng] = center
  return stores
    .filter(s => s.lat != null && s.lng != null)
    .map(s => ({ ...s, distKm: haversineKm(lat, lng, s.lat, s.lng) }))
    .filter(s => s.distKm <= radiusKm)
    .sort((a, b) => a.distKm - b.distKm)
}

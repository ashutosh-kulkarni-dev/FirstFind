// Shared AI-score → color helpers (matches the mockups' legend thresholds).
export function scoreColor(s) {
  if (s == null) return 'var(--score-none)'
  if (s >= 4.5) return 'var(--score-green)'
  if (s >= 4.0) return 'var(--score-lime)'
  if (s >= 3.5) return 'var(--score-amber)'
  return 'var(--score-red)'
}

export function scoreLabel(s) {
  if (s == null) return 'Unrated'
  if (s >= 4.5) return 'Exceptional'
  if (s >= 4.0) return 'Great'
  if (s >= 3.5) return 'Good'
  return 'Below 3.5'
}

// Hex versions for canvas/Leaflet contexts where CSS vars don't resolve.
export function scoreHex(s) {
  if (s == null) return '#94a3b8'
  if (s >= 4.5) return '#22c55e'
  if (s >= 4.0) return '#84cc16'
  if (s >= 3.5) return '#f59e0b'
  return '#f43f5e'
}

// AI-score → colour (matches the mockups' legend thresholds). Hex rather than
// CSS variables because Leaflet markers and popups can't resolve those.
export function scoreHex(s) {
  if (s == null) return '#94a3b8'
  if (s >= 4.5) return '#22c55e'
  if (s >= 4.0) return '#84cc16'
  if (s >= 3.5) return '#f59e0b'
  return '#f43f5e'
}

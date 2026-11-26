// Escape text before it goes into an HTML string (Leaflet popups, tooltips and
// divIcons take raw HTML). Store and station names come from imported data
// (Google, OpenStreetMap), so they must never be trusted as markup.
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ESCAPES[c])
}

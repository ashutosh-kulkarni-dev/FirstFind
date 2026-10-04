import L from 'leaflet'

export function createDarkMap(el) {
  const map = L.map(el, { center: [12.9716, 77.5946], zoom: 12, zoomControl: false, attributionControl: false })
  const tileUrl = import.meta.env.VITE_MAP_TILE_URL
    || 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
  L.tileLayer(tileUrl, { maxZoom: 19 }).addTo(map)
  L.control.zoom({ position: 'bottomleft' }).addTo(map)
  L.control.attribution({ position: 'bottomleft' }).addTo(map)
  return map
}

import { scoreHex } from '../score'

export function storePopupHtml(store) {
  const subtitle = [store.area, store.cat].filter(Boolean).join(' · ')
  const c = scoreHex(store.score)
  const scoreChip = store.score != null
    ? `<span style="display:inline-grid;place-items:center;padding:2px 7px;border-radius:12px;background:${c}22;color:${c};font-size:11px;font-weight:700;">★ ${Number(store.score).toFixed(1)}</span>`
    : ''
  const openChip = store.open != null
    ? `<span style="font-size:11px;color:${store.open ? '#16a34a' : '#94a3b8'};font-weight:600;">${store.open ? 'Open now' : 'Closed'}</span>`
    : ''
  const metaRow = scoreChip || openChip
    ? `<div style="margin-top:6px;display:flex;align-items:center;gap:6px;">${scoreChip}${openChip}</div>`
    : ''
  return `<div style="min-width:160px;font-family:Inter,sans-serif;">
    <div style="font-family:Anton,sans-serif;font-size:16px;color:#0f1a2b;letter-spacing:-.3px;">${(store.name || '').toUpperCase()}</div>
    <div style="margin-top:2px;color:#6c7885;font-size:11.5px;">${subtitle}</div>
    ${metaRow}
    <a href="/store/${store.id}" data-store-id="${store.id}" style="display:inline-block;margin-top:8px;color:#1478d1;font-size:12px;font-weight:700;">View store →</a>
  </div>`
}

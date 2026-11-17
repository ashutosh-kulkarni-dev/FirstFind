import { del, patch, post, req, reqBlob } from './client'

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, v) })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const adminApi = {
  adminMeta: () => req('/api/admin/meta'),
  adminStats: () => req('/api/admin/stats'),
  adminStores: (params) => req(`/api/admin/stores${qs(params)}`),
  adminStore: (id) => req(`/api/admin/stores/${encodeURIComponent(id)}`),
  adminCreateStore: (body) => post('/api/admin/stores', body),
  adminUpdateStore: (id, changes) => patch(`/api/admin/stores/${encodeURIComponent(id)}`, changes),
  adminDeleteStore: (id) => del(`/api/admin/stores/${encodeURIComponent(id)}${qs({ confirm: id })}`),
  adminReviews: (params) => req(`/api/admin/reviews${qs(params)}`),
  adminSetReviewHidden: (id, isHidden) => patch(`/api/admin/reviews/${id}`, { is_hidden: isHidden }),
  adminDeleteReview: (id) => del(`/api/admin/reviews/${id}`),
  adminAttention: () => req('/api/admin/attention'),
  adminAudit: (params) => req(`/api/admin/audit${qs(params)}`),
  adminExportStores: () => reqBlob('/api/admin/export/stores.csv'),
}

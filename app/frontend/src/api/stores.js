import { post, req } from './client'

export const storesApi = {
  stores: (params = {}, opts = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null))
    return req(`/api/stores?${qs}`, opts)
  },
  areas: () => req('/api/stores/areas'),
  facets: () => req('/api/stores/facets'),
  store: (id) => req(`/api/stores/${id}`),
  addReview: (id, rating, text) => post(`/api/stores/${id}/reviews`, { rating, text }),
  saveStore: (id) => post(`/api/stores/${id}/save`),
  recommendations: () => req('/api/recommendations'),
}

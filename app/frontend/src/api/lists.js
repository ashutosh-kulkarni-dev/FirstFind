import { del, patch, post, req } from './client'

export const listsApi = {
  createList: (body) => post('/api/lists', body),
  lists: () => req('/api/lists'),
  list: (id) => req(`/api/lists/${id}`),
  updateList: (id, changes) => patch(`/api/lists/${id}`, changes),
  deleteList: (id) => del(`/api/lists/${id}`),
}

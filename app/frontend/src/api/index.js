// One import for the whole app: `import { api } from '../api'`.
// Each area's calls live in its own file; add new endpoints there.
import { adminApi } from './admin'
import { authApi } from './auth'
import { chatApi } from './chat'
import { listsApi } from './lists'
import { mapApi } from './map'
import { storesApi } from './stores'

export const api = { ...adminApi, ...authApi, ...storesApi, ...mapApi, ...listsApi, ...chatApi }

export { AUTH_UNAUTHORIZED_EVENT, getToken, getUser, setAuth } from './client'
export { resetSession } from './chat'

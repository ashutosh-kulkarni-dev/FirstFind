import { post, req } from './client'

export const authApi = {
  register: (name, email, password) => post('/api/auth/register', { name, email, password }),
  login: (email, password) => post('/api/auth/login', { email, password }),
  google: (credential) => post('/api/auth/google', { credential }),
  me: () => req('/api/auth/me'),
}

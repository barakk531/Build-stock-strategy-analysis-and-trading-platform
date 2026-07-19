import axios from 'axios'

// Default is a relative path served through the Vite dev proxy (see
// vite.config.js); set VITE_API_BASE_URL to hit a backend directly instead.
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const KEY_STORAGE = 'stocks.apiKey'

export function getApiKey() {
  return localStorage.getItem(KEY_STORAGE) || ''
}

export function setApiKey(key) {
  if (key) localStorage.setItem(KEY_STORAGE, key)
  else localStorage.removeItem(KEY_STORAGE)
}

export const api = axios.create({ baseURL, timeout: 10000 })

// When the server has ADMIN_API_KEY configured, guarded endpoints need this
// header; harmless to send when auth is disabled.
api.interceptors.request.use((config) => {
  const key = getApiKey()
  if (key) config.headers['X-API-Key'] = key
  return config
})

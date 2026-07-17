import axios from 'axios'

// Default is a relative path served through the Vite dev proxy (see
// vite.config.js); set VITE_API_BASE_URL to hit a backend directly instead.
const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({ baseURL, timeout: 10000 })

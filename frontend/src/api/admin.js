import { api } from './client.js'

export async function getDataHealth() {
  const { data } = await api.get('/admin/data-health')
  return data
}

export async function getHealthReport() {
  const { data } = await api.get('/admin/health-report')
  return data
}

export async function getJobs() {
  const { data } = await api.get('/admin/jobs')
  return data
}

export async function getConfig() {
  const { data } = await api.get('/admin/config')
  return data
}

// Manual pipeline triggers. Long-running steps get generous timeouts.
export const actions = {
  syncUniverse: () => api.post('/admin/universe/sync', null, { timeout: 120000 }),
  syncPrices: () => api.post('/admin/prices/sync', null, { timeout: 600000 }),
  recalcIndicators: () => api.post('/admin/indicators/recalculate', null, { timeout: 600000 }),
  scanSignals: () => api.post('/admin/signals/scan', null, { timeout: 600000 }),
  telegramQueue: () => api.post('/admin/telegram/queue'),
  telegramProcess: () => api.post('/admin/telegram/process'),
  telegramTest: () => api.post('/admin/telegram/test'),
  paperProcess: () => api.post('/admin/paper/process', null, { timeout: 600000 }),
}

import { api } from './client.js'

export async function listPaperAccounts() {
  const { data } = await api.get('/paper-accounts')
  return data
}

export async function getPaperAccount(id) {
  const { data } = await api.get(`/paper-accounts/${id}`)
  return data
}

export async function createPaperAccount(payload) {
  const { data } = await api.post('/paper-accounts', payload)
  return data
}

export async function updatePaperAccount(id, payload) {
  const { data } = await api.put(`/paper-accounts/${id}`, payload)
  return data
}

export async function deletePaperAccount(id) {
  await api.delete(`/paper-accounts/${id}`)
}

export async function pausePaperAccount(id) {
  const { data } = await api.post(`/paper-accounts/${id}/pause`)
  return data
}

export async function resumePaperAccount(id) {
  const { data } = await api.post(`/paper-accounts/${id}/resume`)
  return data
}

export async function processPaperAccount(id) {
  // Catch-up replays can take a while on first run.
  const { data } = await api.post(`/paper-accounts/${id}/process`, null, { timeout: 120000 })
  return data
}

export async function getPaperPositions(id, params) {
  const { data } = await api.get(`/paper-accounts/${id}/positions`, { params })
  return data
}

export async function getPaperOrders(id, params) {
  const { data } = await api.get(`/paper-accounts/${id}/orders`, { params })
  return data
}

export async function getPaperPerformance(id) {
  const { data } = await api.get(`/paper-accounts/${id}/performance`)
  return data
}

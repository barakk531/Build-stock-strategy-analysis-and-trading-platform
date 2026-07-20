import { api } from './client.js'

export async function listStrategies() {
  const { data } = await api.get('/strategies')
  return data
}

export async function getStrategy(id) {
  const { data } = await api.get(`/strategies/${id}`)
  return data
}

// What-if evaluation: run the strategy on one symbol with optional parameter
// overrides. Nothing is persisted server-side.
export async function evaluateStrategy(id, payload) {
  const { data } = await api.post(`/strategies/${id}/evaluate`, payload)
  return data
}

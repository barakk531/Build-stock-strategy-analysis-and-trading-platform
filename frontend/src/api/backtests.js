import { api } from './client.js'

export async function listBacktests(params) {
  const { data } = await api.get('/backtests', { params })
  return data
}

export async function getBacktest(id) {
  const { data } = await api.get(`/backtests/${id}`)
  return data
}

export async function createBacktest(payload) {
  const { data } = await api.post('/backtests', payload)
  return data
}

export async function deleteBacktest(id) {
  await api.delete(`/backtests/${id}`)
}

export async function getBacktestTrades(id, params) {
  const { data } = await api.get(`/backtests/${id}/trades`, { params })
  return data
}

export async function getBacktestSkips(id, params) {
  const { data } = await api.get(`/backtests/${id}/skips`, { params })
  return data
}

export async function listStrategies() {
  const { data } = await api.get('/strategies')
  return data
}

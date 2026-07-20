import { api } from './client.js'

export async function getSignals(params) {
  const { data } = await api.get('/signals', { params })
  return data
}

export async function getLatestSignals(params) {
  const { data } = await api.get('/signals/latest', { params })
  return data
}

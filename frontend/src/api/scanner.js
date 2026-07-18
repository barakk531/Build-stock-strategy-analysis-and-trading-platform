import { api } from './client.js'

export async function getScanner(params) {
  const { data } = await api.get('/scanner', { params })
  return data
}

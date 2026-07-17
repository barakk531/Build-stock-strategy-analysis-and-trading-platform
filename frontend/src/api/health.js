import { api } from './client.js'

export async function getHealth() {
  const { data } = await api.get('/health')
  return data
}

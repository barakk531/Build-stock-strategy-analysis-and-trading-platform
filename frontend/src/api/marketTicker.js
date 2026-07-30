import { api } from './client.js'

// Lightweight ticker feed (latest stored daily close). Read-only; the backend
// reads DB values, so calling this often does not hit Yahoo Finance.
export async function getMarketTicker(params) {
  const { data } = await api.get('/market-ticker', { params })
  return data
}

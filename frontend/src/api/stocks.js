import { api } from './client.js'

export async function getStock(symbol) {
  const { data } = await api.get(`/stocks/${symbol}`)
  return data
}

export async function getStockPrices(symbol, params) {
  const { data } = await api.get(`/stocks/${symbol}/prices`, { params })
  return data
}

export async function getStockIndicators(symbol, params) {
  const { data } = await api.get(`/stocks/${symbol}/indicators`, { params })
  return data
}

export async function getStockSignals(symbol, params) {
  const { data } = await api.get(`/stocks/${symbol}/signals`, { params })
  return data
}

export async function getStockAnalysis(symbol) {
  const { data } = await api.get(`/stocks/${symbol}/analysis`)
  return data
}

export async function listStocks(params) {
  const { data } = await api.get('/stocks', { params })
  return data
}

// Fetch every stock across all pages (the endpoint caps limit at 500). Used to
// build a complete stock_id -> symbol map (e.g. the Signals page).
export async function listAllStocks() {
  const pageSize = 500
  const items = []
  let offset = 0
  // Cap the loop defensively; the universe is ~500 stocks.
  for (let page = 0; page < 20; page++) {
    const { data } = await api.get('/stocks', { params: { limit: pageSize, offset } })
    items.push(...(data.items ?? []))
    offset += pageSize
    if (!data.items?.length || items.length >= (data.total ?? items.length)) break
  }
  return items
}

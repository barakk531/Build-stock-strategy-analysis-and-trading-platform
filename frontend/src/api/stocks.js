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

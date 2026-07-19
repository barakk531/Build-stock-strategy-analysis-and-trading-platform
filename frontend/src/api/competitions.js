import { api } from './client.js'

export async function listCompetitions() {
  const { data } = await api.get('/competitions')
  return data
}

export async function createCompetition(payload) {
  const { data } = await api.post('/competitions', payload)
  return data
}

export async function deleteCompetition(id) {
  await api.delete(`/competitions/${id}`)
}

export async function getLeaderboard(id) {
  const { data } = await api.get(`/competitions/${id}/leaderboard`)
  return data
}

export async function addCompetitionAccount(id, accountId) {
  const { data } = await api.post(`/competitions/${id}/accounts/${accountId}`)
  return data
}

export async function removeCompetitionAccount(id, accountId) {
  const { data } = await api.delete(`/competitions/${id}/accounts/${accountId}`)
  return data
}

export async function cloneAccount(accountId, payload) {
  const { data } = await api.post(`/paper-accounts/${accountId}/clone`, payload)
  return data
}

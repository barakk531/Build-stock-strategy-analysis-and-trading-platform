import { create } from 'zustand'

// Lightweight global UI state. Server state belongs in TanStack Query, not here.
// The watchlist is symbols only, persisted to localStorage.

const WATCHLIST_KEY = 'stocks.watchlist'

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export const useAppStore = create((set, get) => ({
  watchlist: loadWatchlist(),
  toggleWatch: (symbol) => {
    const current = get().watchlist
    const next = current.includes(symbol)
      ? current.filter((s) => s !== symbol)
      : [...current, symbol]
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(next))
    set({ watchlist: next })
  },
  isWatched: (symbol) => get().watchlist.includes(symbol),
}))

import { create } from 'zustand'

// Lightweight global UI state. Server state belongs in TanStack Query, not here.
export const useAppStore = create(() => ({
  // Nothing global yet — first real fields arrive with the scanner (Phase 4),
  // e.g. saved filter presets and watchlist UI state.
}))

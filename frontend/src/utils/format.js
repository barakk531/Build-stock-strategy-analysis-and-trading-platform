// Human-readable market cap / large-number formatting, e.g. $950M, $12.4B, $2.1T.
const UNITS = [
  { value: 1e12, suffix: 'T' },
  { value: 1e9, suffix: 'B' },
  { value: 1e6, suffix: 'M' },
  { value: 1e3, suffix: 'K' },
]

export function formatMarketCap(value) {
  if (value == null || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  for (const { value: unit, suffix } of UNITS) {
    if (abs >= unit) {
      const scaled = value / unit
      return `$${scaled >= 100 ? Math.round(scaled) : scaled.toFixed(1)}${suffix}`
    }
  }
  return `$${value}`
}

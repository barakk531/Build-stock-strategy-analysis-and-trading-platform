// Formatting for financial values. Market caps read as $950M / $12.4B / $2.1T.

const CAP_UNITS = [
  { value: 1e12, suffix: 'T' },
  { value: 1e9, suffix: 'B' },
  { value: 1e6, suffix: 'M' },
  { value: 1e3, suffix: 'K' },
]

export function formatMarketCap(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const number = Number(value)
  const abs = Math.abs(number)
  for (const { value: unit, suffix } of CAP_UNITS) {
    if (abs >= unit) {
      const scaled = number / unit
      const rounded = Math.abs(scaled) >= 100 ? Math.round(scaled) : scaled.toFixed(1)
      // Re-check the boundary: 999.95e9 rounds to 1000.0B -> promote to 1.0T.
      if (Math.abs(Number(rounded)) >= 1000 && unit !== 1e12) continue
      return `$${rounded}${suffix}`
    }
  }
  return `$${number}`
}

export function formatCompact(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(
    Number(value),
  )
}

export function formatPrice(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

export function formatPercent(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  const number = Number(value)
  const sign = number > 0 ? '+' : ''
  return `${sign}${number.toFixed(digits)}%`
}

export function formatMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export function formatRatio(value) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toFixed(2)
}

export function changeClass(value) {
  if (value == null) return 'text-slate-400'
  if (value > 0) return 'text-emerald-400'
  if (value < 0) return 'text-red-400'
  return 'text-slate-300'
}

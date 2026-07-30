import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getScanner } from '../api/scanner.js'
import StatusBadge from '../components/StatusBadge.jsx'
import { useAppStore } from '../stores/appStore.js'
import { changeClass, formatMarketCap, formatPercent, formatPrice } from '../utils/format.js'

const PAGE_SIZE = 50

const CAP_PRESETS = [
  { label: 'Any cap', min: '', max: '' },
  { label: 'Under $2B', min: '', max: 2e9 },
  { label: '$2B–$10B', min: 2e9, max: 10e9 },
  { label: '$10B–$50B', min: 10e9, max: 50e9 },
  { label: '$50B–$200B', min: 50e9, max: 200e9 },
  { label: 'Above $200B', min: 200e9, max: '' },
]

const SORTS = [
  ['symbol', 'Symbol'],
  ['market_cap', 'Market cap'],
  ['close', 'Price'],
  ['change_pct', 'Change %'],
  ['volume_ratio', 'Volume ratio'],
  ['sma_150_slope', 'SMA150 slope'],
  ['distance_sma_150_pct', 'Dist. SMA150'],
  ['latest_signal_date', 'Signal date'],
]

function Th({ label, sortKey, params, onSort, className = '' }) {
  // Label-only columns (★, Company, Sector, the SMAs, State) render without a
  // `params` prop and are never the active sort — guard both reads so a
  // missing `params` can't crash the whole table.
  const active = sortKey && params?.sort === sortKey
  const arrow = active ? (params?.order === 'desc' ? ' ↓' : ' ↑') : ''
  return (
    <th
      onClick={sortKey ? () => onSort(sortKey) : undefined}
      className={`whitespace-nowrap px-2 py-2 text-left text-[11px] font-medium tracking-wide text-slate-400 uppercase ${
        sortKey ? 'cursor-pointer select-none hover:text-slate-200' : ''
      } ${active ? 'text-emerald-400' : ''} ${className}`}
    >
      {label}
      {arrow}
    </th>
  )
}

export default function Scanner() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { watchlist, toggleWatch } = useAppStore()
  const [watchOnly, setWatchOnly] = useState(false)

  const params = useMemo(() => {
    const p = { sort: 'symbol', order: 'asc', page: '1' }
    for (const [key, value] of searchParams.entries()) p[key] = value
    return p
  }, [searchParams])

  const page = Math.max(1, parseInt(params.page, 10) || 1)

  const queryParams = useMemo(() => {
    // Watch-only filters client-side, so fetch the whole universe (the endpoint
    // caps limit at 520) instead of one 50-row page — otherwise starred stocks
    // that fall on other pages are invisible.
    const q = {
      sort: params.sort,
      order: params.order,
      limit: watchOnly ? 520 : PAGE_SIZE,
      offset: watchOnly ? 0 : (page - 1) * PAGE_SIZE,
    }
    for (const key of [
      'search', 'sector', 'signal_type', 'price_vs_sma150', 'sma20_vs_sma50',
      'slope', 'min_volume_ratio', 'min_market_cap', 'max_market_cap',
    ]) {
      if (params[key]) q[key] = params[key]
    }
    if (params.buy_state === '1') q.buy_state = true
    if (params.sell_state === '1') q.sell_state = true
    return q
  }, [params, page, watchOnly])

  const { data, isPending, isError, error } = useQuery({
    queryKey: ['scanner', queryParams],
    queryFn: () => getScanner(queryParams),
    placeholderData: (prev) => prev,
    refetchInterval: 60_000,
  })

  function patchParams(patch) {
    const next = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(patch)) {
      if (value === '' || value == null || value === false) next.delete(key)
      else next.set(key, String(value))
    }
    if (!('page' in patch)) next.set('page', '1')
    setSearchParams(next, { replace: true })
  }

  function onSort(key) {
    if (params.sort === key) patchParams({ order: params.order === 'asc' ? 'desc' : 'asc' })
    else patchParams({ sort: key, order: key === 'symbol' ? 'asc' : 'desc' })
  }

  const rows = useMemo(() => {
    const items = data?.items ?? []
    return watchOnly ? items.filter((r) => watchlist.includes(r.symbol)) : items
  }, [data, watchOnly, watchlist])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const capPreset = CAP_PRESETS.findIndex(
    (p) => String(p.min) === (params.min_market_cap ?? '') && String(p.max) === (params.max_market_cap ?? ''),
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-2xl font-semibold">Scanner</h1>
        <p className="text-xs text-slate-500">
          {data
            ? `${watchOnly ? `${rows.length} watched` : `${data.total} matches`} · S&P 500 · data ${data.items[0]?.trade_date ?? ''}`
            : ''}
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 p-3 text-sm">
        <input
          defaultValue={params.search ?? ''}
          onChange={(e) => {
            clearTimeout(window.__scanTimer)
            const value = e.target.value
            window.__scanTimer = setTimeout(() => patchParams({ search: value }), 350)
          }}
          placeholder="Search symbol or company…"
          className="w-56 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100 placeholder:text-slate-500 focus:border-emerald-500 focus:outline-none"
        />
        <select
          value={params.sector ?? ''}
          onChange={(e) => patchParams({ sector: e.target.value })}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
        >
          <option value="">All sectors</option>
          {(data?.sectors ?? []).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={capPreset === -1 ? '' : capPreset}
          onChange={(e) => {
            const preset = CAP_PRESETS[Number(e.target.value)] ?? CAP_PRESETS[0]
            patchParams({ min_market_cap: preset.min, max_market_cap: preset.max })
          }}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
        >
          {CAP_PRESETS.map((p, i) => (
            <option key={p.label} value={i}>{p.label}</option>
          ))}
        </select>
        <select
          value={params.slope ?? ''}
          onChange={(e) => patchParams({ slope: e.target.value })}
          className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5"
        >
          <option value="">Any slope</option>
          <option value="positive">SMA150 rising</option>
          <option value="flat">SMA150 flat</option>
          <option value="negative">SMA150 falling</option>
        </select>
        <input
          type="number" min="0" step="0.1"
          value={params.min_volume_ratio ?? ''}
          onChange={(e) => patchParams({ min_volume_ratio: e.target.value })}
          placeholder="Min vol ratio"
          className="w-28 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 placeholder:text-slate-500"
        />
        {[
          ['buy_state', 'Buy state', 'text-emerald-400 border-emerald-500/40'],
          ['sell_state', 'Sell state', 'text-red-400 border-red-500/40'],
        ].map(([key, label, cls]) => (
          <button
            key={key}
            onClick={() => patchParams({ [key]: params[key] === '1' ? '' : '1' })}
            className={`rounded border px-2 py-1.5 text-xs ${
              params[key] === '1' ? `${cls} bg-slate-800` : 'border-slate-700 text-slate-400 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
        <button
          onClick={() => setWatchOnly((v) => !v)}
          className={`rounded border px-2 py-1.5 text-xs ${
            watchOnly ? 'border-amber-500/40 bg-slate-800 text-amber-400' : 'border-slate-700 text-slate-400 hover:text-slate-200'
          }`}
        >
          ★ Watchlist ({watchlist.length})
        </button>
        <button
          onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
          className="ml-auto rounded border border-slate-700 px-2 py-1.5 text-xs text-slate-400 hover:text-slate-200"
        >
          Reset
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900">
        {isPending && <p className="p-6 text-sm text-slate-400">Loading scanner…</p>}
        {isError && (
          <p className="p-6 text-sm text-red-400">Scanner failed: {error?.message}</p>
        )}
        {data && rows.length === 0 && (
          <p className="p-6 text-sm text-slate-400">
            No stocks match these filters. Loosen a filter or press Reset.
          </p>
        )}
        {data && rows.length > 0 && (
          <table className="w-full text-sm tabular-nums">
            <thead className="border-b border-slate-800">
              <tr>
                <Th label="★" />
                <Th label="Symbol" sortKey="symbol" params={params} onSort={onSort} />
                <Th label="Company" />
                <Th label="Price" sortKey="close" params={params} onSort={onSort} className="text-right" />
                <Th label="Chg %" sortKey="change_pct" params={params} onSort={onSort} className="text-right" />
                <Th label="Mkt cap" sortKey="market_cap" params={params} onSort={onSort} className="text-right" />
                <Th label="Sector" />
                <Th label="SMA20" className="text-right" />
                <Th label="SMA50" className="text-right" />
                <Th label="SMA150" className="text-right" />
                <Th label="Dist 150" sortKey="distance_sma_150_pct" params={params} onSort={onSort} className="text-right" />
                <Th label="Slope" sortKey="sma_150_slope" params={params} onSort={onSort} className="text-right" />
                <Th label="Vol ratio" sortKey="volume_ratio" params={params} onSort={onSort} className="text-right" />
                <Th label="State" />
                <Th label="Last signal" sortKey="latest_signal_date" params={params} onSort={onSort} />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {rows.map((row) => (
                <tr
                  key={row.symbol}
                  onClick={() => navigate(`/stocks/${row.symbol}`)}
                  className="cursor-pointer hover:bg-slate-800/50"
                >
                  <td className="px-2 py-1.5" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => toggleWatch(row.symbol)}
                      className={watchlist.includes(row.symbol) ? 'text-amber-400' : 'text-slate-600 hover:text-slate-400'}
                      aria-label={`Watch ${row.symbol}`}
                    >
                      ★
                    </button>
                  </td>
                  <td className="px-2 py-1.5 font-medium text-slate-100">
                    <Link to={`/stocks/${row.symbol}`} onClick={(e) => e.stopPropagation()}>
                      {row.symbol}
                    </Link>
                  </td>
                  <td className="max-w-44 truncate px-2 py-1.5 text-slate-400">{row.company_name}</td>
                  <td className="px-2 py-1.5 text-right">{formatPrice(row.close)}</td>
                  <td className={`px-2 py-1.5 text-right ${changeClass(row.change_pct)}`}>
                    {formatPercent(row.change_pct)}
                  </td>
                  <td className="px-2 py-1.5 text-right text-slate-300">{formatMarketCap(row.market_cap)}</td>
                  <td className="max-w-36 truncate px-2 py-1.5 text-slate-400">{row.sector}</td>
                  <td className="px-2 py-1.5 text-right text-slate-400">{formatPrice(row.sma_20)}</td>
                  <td className="px-2 py-1.5 text-right text-slate-400">{formatPrice(row.sma_50)}</td>
                  <td className="px-2 py-1.5 text-right text-slate-400">{formatPrice(row.sma_150)}</td>
                  <td className={`px-2 py-1.5 text-right ${changeClass(row.distance_sma_150_pct)}`}>
                    {formatPercent(row.distance_sma_150_pct, 1)}
                  </td>
                  <td className={`px-2 py-1.5 text-right ${changeClass(row.sma_150_slope)}`}>
                    {formatPercent(row.sma_150_slope, 2)}
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    {row.volume_ratio != null ? `${row.volume_ratio.toFixed(2)}x` : '—'}
                  </td>
                  <td className="px-2 py-1.5">
                    {row.buy_state && <StatusBadge kind="ok">BUY</StatusBadge>}
                    {row.sell_state && <StatusBadge kind="down">SELL</StatusBadge>}
                    {!row.buy_state && !row.sell_state && <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-2 py-1.5 text-xs text-slate-400">
                    {row.latest_signal_type ? (
                      <span className={row.latest_signal_type === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>
                        {row.latest_signal_type} {row.latest_signal_date}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination (watch-only shows the whole filtered set on one page) */}
      {!watchOnly && data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-slate-400">
          <button
            disabled={page <= 1}
            onClick={() => patchParams({ page: page - 1 })}
            className="rounded border border-slate-700 px-3 py-1.5 hover:text-slate-200 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span>
            Page {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => patchParams({ page: page + 1 })}
            className="rounded border border-slate-700 px-3 py-1.5 hover:text-slate-200 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}

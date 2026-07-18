import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  getStock,
  getStockAnalysis,
  getStockIndicators,
  getStockPrices,
  getStockSignals,
  listStocks,
} from '../api/stocks.js'
import PriceChart from '../charts/PriceChart.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { useAppStore } from '../stores/appStore.js'
import { changeClass, formatCompact, formatMarketCap, formatPercent, formatPrice } from '../utils/format.js'

// Chart range is a DISPLAY choice only — strategy parameters never change with it.
const RANGES = [
  { label: '1Y', years: 1 },
  { label: '3Y', years: 3 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: 10 },
  { label: '20Y', years: 20 },
  { label: 'MAX', years: null },
]

function startFor(years) {
  if (!years) return undefined
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

function Condition({ c }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span className="flex items-center gap-2">
        <span className={c.passed ? 'text-emerald-400' : 'text-red-400'}>
          {c.passed ? '✓' : '✗'}
        </span>
        <span className="text-slate-300">{c.label}</span>
      </span>
      <span className="text-xs text-slate-400 tabular-nums">
        {c.actual != null ? formatCompact(c.actual) : '—'} {c.comparison}{' '}
        {c.threshold != null ? formatCompact(c.threshold) : '—'}
      </span>
    </div>
  )
}

export default function StockDetail() {
  const { symbol } = useParams()
  const navigate = useNavigate()
  const { watchlist, toggleWatch } = useAppStore()
  const [range, setRange] = useState('5Y')
  const [show, setShow] = useState({ sma20: true, sma50: true, sma150: true, volume: true, buys: true, sells: true })

  const years = RANGES.find((r) => r.label === range)?.years
  const start = startFor(years)

  const stockQ = useQuery({ queryKey: ['stock', symbol], queryFn: () => getStock(symbol) })
  const pricesQ = useQuery({
    queryKey: ['prices', symbol, range],
    queryFn: () => getStockPrices(symbol, { start }),
  })
  const indicatorsQ = useQuery({
    queryKey: ['indicators', symbol, range],
    queryFn: () => getStockIndicators(symbol, { start }),
  })
  const signalsQ = useQuery({
    queryKey: ['signals', symbol],
    queryFn: () => getStockSignals(symbol, { limit: 500 }),
  })
  const analysisQ = useQuery({
    queryKey: ['analysis', symbol],
    queryFn: () => getStockAnalysis(symbol),
  })
  const allStocksQ = useQuery({
    queryKey: ['all-symbols'],
    queryFn: () => listStocks({ limit: 510 }),
    staleTime: 5 * 60_000,
  })

  const chartData = useMemo(() => {
    const prices = pricesQ.data?.prices ?? []
    const candles = prices
      .filter((p) => p.open != null && p.close != null)
      .map((p) => ({ time: p.trade_date, open: p.open, high: p.high, low: p.low, close: p.close }))
    const bars = prices.map((p) => ({ time: p.trade_date, value: p.volume ?? 0 }))
    const indicators = indicatorsQ.data?.indicators ?? []
    const line = (key) =>
      indicators.filter((i) => i[key] != null).map((i) => ({ time: i.trade_date, value: i[key] }))
    const priceDates = new Set(prices.map((p) => p.trade_date))
    const markers = (signalsQ.data?.items ?? [])
      .filter((s) => priceDates.has(s.trade_date))
      .sort((a, b) => (a.trade_date < b.trade_date ? -1 : 1))
      .map((s) => ({
        time: s.trade_date,
        signalType: s.signal_type,
        price: s.reference_price != null ? formatPrice(s.reference_price) : '',
      }))
    return {
      candles,
      smas: { sma20: line('sma_20'), sma50: line('sma_50'), sma150: line('sma_150') },
      volume: { bars, average: line('average_volume') },
      markers,
    }
  }, [pricesQ.data, indicatorsQ.data, signalsQ.data])

  const neighbors = useMemo(() => {
    const symbols = (allStocksQ.data?.items ?? []).map((s) => s.symbol)
    const i = symbols.indexOf(symbol?.toUpperCase())
    return {
      prev: i > 0 ? symbols[i - 1] : null,
      next: i >= 0 && i < symbols.length - 1 ? symbols[i + 1] : null,
    }
  }, [allStocksQ.data, symbol])

  const stock = stockQ.data
  const analysis = analysisQ.data
  const latestPrice = pricesQ.data?.prices?.at(-1)
  const prevPrice = pricesQ.data?.prices?.at(-2)
  const changePct =
    latestPrice && prevPrice ? (latestPrice.adjusted_close / prevPrice.adjusted_close - 1) * 100 : null

  if (stockQ.isPending) return <p className="text-sm text-slate-400">Loading {symbol}…</p>
  if (stockQ.isError)
    return (
      <div className="space-y-2">
        <p className="text-sm text-red-400">Unknown symbol: {symbol}</p>
        <Link to="/scanner" className="text-sm text-emerald-400">← Back to scanner</Link>
      </div>
    )

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          onClick={() => toggleWatch(stock.symbol)}
          className={`text-xl ${watchlist.includes(stock.symbol) ? 'text-amber-400' : 'text-slate-600 hover:text-slate-400'}`}
          aria-label="Toggle watchlist"
        >
          ★
        </button>
        <h1 className="text-2xl font-semibold">{stock.symbol}</h1>
        <span className="text-slate-400">{stock.company_name}</span>
        {latestPrice && (
          <span className="text-xl tabular-nums">{formatPrice(latestPrice.close)}</span>
        )}
        <span className={`tabular-nums ${changeClass(changePct)}`}>{formatPercent(changePct)}</span>
        <span className="text-sm text-slate-400">{formatMarketCap(stock.market_cap)}</span>
        <span className="text-xs text-slate-500">
          {stock.sector}{stock.industry ? ` · ${stock.industry}` : ''}
        </span>
        <span className="ml-auto flex gap-2 text-sm">
          <button
            disabled={!neighbors.prev}
            onClick={() => navigate(`/stocks/${neighbors.prev}`)}
            className="rounded border border-slate-700 px-2 py-1 text-slate-400 hover:text-slate-100 disabled:opacity-30"
          >
            ← {neighbors.prev ?? ''}
          </button>
          <button
            disabled={!neighbors.next}
            onClick={() => navigate(`/stocks/${neighbors.next}`)}
            className="rounded border border-slate-700 px-2 py-1 text-slate-400 hover:text-slate-100 disabled:opacity-30"
          >
            {neighbors.next ?? ''} →
          </button>
        </span>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {RANGES.map((r) => (
          <button
            key={r.label}
            onClick={() => setRange(r.label)}
            className={`rounded px-2.5 py-1 ${
              range === r.label
                ? 'bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {r.label}
          </button>
        ))}
        <span className="mx-2 h-4 w-px bg-slate-800" />
        {[
          ['sma20', 'SMA 20', 'text-amber-400'],
          ['sma50', 'SMA 50', 'text-sky-400'],
          ['sma150', 'SMA 150', 'text-violet-400'],
          ['volume', 'Volume', 'text-slate-300'],
          ['buys', 'Buy marks', 'text-emerald-400'],
          ['sells', 'Sell marks', 'text-red-400'],
        ].map(([key, label, cls]) => (
          <label key={key} className={`flex cursor-pointer items-center gap-1 ${cls}`}>
            <input
              type="checkbox"
              checked={show[key]}
              onChange={() => setShow((s) => ({ ...s, [key]: !s[key] }))}
              className="accent-emerald-500"
            />
            {label}
          </label>
        ))}
      </div>

      {/* Chart */}
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-2">
        {pricesQ.isPending ? (
          <p className="p-6 text-sm text-slate-400">Loading chart…</p>
        ) : (
          <PriceChart {...chartData} show={show} />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Analysis panel */}
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
              Signal conditions
            </h2>
            {analysis && <span className="text-xs text-slate-500">{analysis.strategy_name} · {analysis.as_of}</span>}
          </div>
          {analysisQ.isPending && <p className="mt-3 text-sm text-slate-400">Evaluating…</p>}
          {analysisQ.isError && (
            <p className="mt-3 text-sm text-slate-400">No analysis available yet for this symbol.</p>
          )}
          {analysis && (
            <div className="mt-3 space-y-4">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">Buy conditions</span>
                  <StatusBadge kind={analysis.buy.state ? 'ok' : 'loading'}>
                    {analysis.buy.state ? 'IN BUY STATE' : 'not in buy state'}
                  </StatusBadge>
                </div>
                <div className="divide-y divide-slate-800/60">
                  {analysis.buy.conditions.map((c) => <Condition key={c.key} c={c} />)}
                </div>
              </div>
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">Sell conditions</span>
                  <StatusBadge kind={analysis.sell.state ? 'down' : 'loading'}>
                    {analysis.sell.state ? 'IN SELL STATE' : 'not in sell state'}
                  </StatusBadge>
                </div>
                <div className="divide-y divide-slate-800/60">
                  {analysis.sell.conditions.map((c) => <Condition key={c.key} c={c} />)}
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Signal history */}
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
            Signal history
          </h2>
          {signalsQ.isPending && <p className="mt-3 text-sm text-slate-400">Loading signals…</p>}
          {signalsQ.data && signalsQ.data.items.length === 0 && (
            <p className="mt-3 text-sm text-slate-400">
              No historical signals for this symbol under the default strategy.
            </p>
          )}
          {signalsQ.data && signalsQ.data.items.length > 0 && (
            <div className="mt-2 max-h-80 overflow-y-auto">
              <table className="w-full text-sm tabular-nums">
                <thead className="text-left text-[11px] text-slate-500 uppercase">
                  <tr>
                    <th className="py-1 pr-2">Date</th>
                    <th className="py-1 pr-2">Type</th>
                    <th className="py-1 pr-2 text-right">Ref close</th>
                    <th className="py-1">Execution</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {signalsQ.data.items.map((s) => (
                    <tr key={s.id}>
                      <td className="py-1.5 pr-2 text-slate-300">{s.trade_date}</td>
                      <td className="py-1.5 pr-2">
                        <span className={s.signal_type === 'BUY' ? 'text-emerald-400' : 'text-red-400'}>
                          {s.signal_type}
                        </span>
                      </td>
                      <td className="py-1.5 pr-2 text-right text-slate-300">
                        {formatPrice(s.reference_price)}
                      </td>
                      <td className="py-1.5 text-xs text-slate-500">
                        {s.execution_date ?? 'next open (pending)'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

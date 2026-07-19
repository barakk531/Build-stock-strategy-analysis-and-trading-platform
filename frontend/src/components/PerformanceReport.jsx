import { Link } from 'react-router-dom'
import EquityChart from '../charts/EquityChart.jsx'
import { changeClass, formatMoney, formatPercent, formatPrice, formatRatio } from '../utils/format.js'

// Shared results renderer: backtest runs and paper accounts emit the same
// shape (metrics, equity/benchmark curves, monthly/yearly returns, open
// positions, notes), so they read identically — the basis for comparison.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function MetricCard({ label, value, cls }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${cls ?? 'text-slate-100'}`}>{value}</p>
    </div>
  )
}

function MonthlyReturns({ monthly }) {
  if (!monthly?.length) return null
  const byYear = new Map()
  for (const { year, month, return_pct } of monthly) {
    if (!byYear.has(year)) byYear.set(year, {})
    byYear.get(year)[month] = return_pct
  }
  const years = [...byYear.keys()].sort((a, b) => b - a)
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full min-w-[760px] text-xs">
        <thead className="bg-slate-900 text-slate-400 uppercase">
          <tr>
            <th className="px-2 py-1.5 text-left">Year</th>
            {MONTHS.map((m) => (
              <th key={m} className="px-2 py-1.5 text-right">{m}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {years.map((year) => (
            <tr key={year}>
              <td className="px-2 py-1.5 font-medium text-slate-300">{year}</td>
              {MONTHS.map((_, i) => {
                const v = byYear.get(year)[i + 1]
                return (
                  <td key={i} className={`px-2 py-1.5 text-right tabular-nums ${changeClass(v)}`}>
                    {v == null ? '·' : v.toFixed(1)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function PerformanceReport({ results, benchmarkSymbol }) {
  const m = results?.metrics
  if (!m) return null
  const equity = (results.equity_curve ?? []).map(([time, value]) => ({ time, value }))
  const drawdown = (results.equity_curve ?? []).map(([time, , dd]) => ({ time, value: dd }))
  const benchmark = (results.benchmark_curve ?? []).map(([time, value]) => ({ time, value }))

  return (
    <>
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <MetricCard label="Final equity" value={formatMoney(m.final_equity)} />
        <MetricCard label="Total return" value={formatPercent(m.total_return_pct)} cls={changeClass(m.total_return_pct)} />
        <MetricCard label="Annualized" value={formatPercent(m.annualized_return_pct)} cls={changeClass(m.annualized_return_pct)} />
        <MetricCard
          label={`Benchmark${benchmarkSymbol ? ` (${benchmarkSymbol})` : ''}`}
          value={formatPercent(m.benchmark_return_pct)}
          cls={changeClass(m.benchmark_return_pct)}
        />
        <MetricCard label="Excess return" value={formatPercent(m.excess_return_pct)} cls={changeClass(m.excess_return_pct)} />
        <MetricCard label="Max drawdown" value={m.max_drawdown_pct == null ? '—' : `${m.max_drawdown_pct.toFixed(2)}%`} cls="text-red-400" />
        <MetricCard label="Sharpe" value={formatRatio(m.sharpe_ratio)} />
        <MetricCard label="Sortino" value={formatRatio(m.sortino_ratio)} />
        <MetricCard label="Volatility (ann.)" value={m.volatility_pct == null ? '—' : `${m.volatility_pct.toFixed(2)}%`} />
        <MetricCard label="Win rate" value={m.win_rate_pct == null ? '—' : `${m.win_rate_pct.toFixed(1)}%`} />
        <MetricCard label="Profit factor" value={formatRatio(m.profit_factor)} />
        <MetricCard label="Trades (closed/open)" value={`${m.trades} / ${m.open_trades}`} />
        <MetricCard label="Avg winner" value={formatMoney(m.average_winner)} cls="text-emerald-400" />
        <MetricCard label="Avg loser" value={formatMoney(m.average_loser)} cls="text-red-400" />
        <MetricCard label="Largest winner" value={formatMoney(m.largest_winner)} cls="text-emerald-400" />
        <MetricCard label="Largest loser" value={formatMoney(m.largest_loser)} cls="text-red-400" />
        <MetricCard label="Avg holding (days)" value={m.average_holding_days ?? '—'} />
        <MetricCard label="Exposure / Turnover" value={`${m.exposure_pct?.toFixed(0) ?? '—'}% / ${formatRatio(m.annual_turnover)}x`} />
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />Equity</span>
          {benchmark.length > 0 && (
            <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-slate-400" />Benchmark (rebased)</span>
          )}
          <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-400" />Drawdown %</span>
        </div>
        <div className="mt-2">
          <EquityChart equity={equity} benchmark={benchmark} drawdown={drawdown} />
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Monthly returns (%)</h2>
        <MonthlyReturns monthly={results.monthly_returns} />
        {results.yearly_returns?.length > 0 && (
          <div className="flex flex-wrap gap-2 pt-1">
            {results.yearly_returns.map(({ year, return_pct }) => (
              <span key={year} className={`rounded border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs tabular-nums ${changeClass(return_pct)}`}>
                {year}: {formatPercent(return_pct, 1)}
              </span>
            ))}
          </div>
        )}
      </section>

      {results.open_positions?.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
            Open positions ({results.open_positions.length})
          </h2>
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2 text-right">Qty</th>
                  <th className="px-3 py-2">Entry</th>
                  <th className="px-3 py-2 text-right">Entry price</th>
                  <th className="px-3 py-2 text-right">Last price</th>
                  <th className="px-3 py-2 text-right">Value</th>
                  <th className="px-3 py-2 text-right">Unrealized</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {results.open_positions.map((p) => (
                  <tr key={p.symbol}>
                    <td className="px-3 py-1.5">
                      <Link to={`/stocks/${p.symbol}`} className="font-medium text-slate-100 hover:text-emerald-400">{p.symbol}</Link>
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{p.quantity}</td>
                    <td className="px-3 py-1.5 text-slate-400">{p.entry_date ?? p.opened_at}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(p.entry_price ?? p.average_entry_price)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(p.last_price)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatMoney(p.market_value)}</td>
                    <td className={`px-3 py-1.5 text-right tabular-nums ${changeClass(p.unrealized_pnl)}`}>{formatMoney(p.unrealized_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {results.notes?.length > 0 && (
        <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
          <h2 className="text-xs font-medium tracking-wide text-amber-400 uppercase">Disclosures</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-400">
            {results.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

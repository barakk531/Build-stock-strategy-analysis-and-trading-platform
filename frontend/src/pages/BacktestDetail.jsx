import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  deleteBacktest,
  getBacktest,
  getBacktestSkips,
  getBacktestTrades,
} from '../api/backtests.js'
import EquityChart from '../charts/EquityChart.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { changeClass, formatPercent, formatPrice } from '../utils/format.js'

const STATUS_KIND = { COMPLETED: 'ok', RUNNING: 'degraded', PENDING: 'degraded', FAILED: 'down' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const PAGE = 50

const fmtMoney = (v) => (v == null ? '—' : `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`)
const fmtRatio = (v) => (v == null ? '—' : Number(v).toFixed(2))

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

function TradesTable({ runId }) {
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const { data } = useQuery({
    queryKey: ['backtest-trades', runId, offset, status],
    queryFn: () => getBacktestTrades(runId, { limit: PAGE, offset, status: status || undefined }),
    placeholderData: (prev) => prev,
  })
  if (!data) return <p className="text-sm text-slate-400">Loading trades…</p>
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs">
        {['', 'closed', 'open'].map((s) => (
          <button
            key={s || 'all'}
            onClick={() => { setStatus(s); setOffset(0) }}
            className={`rounded border px-2 py-0.5 ${status === s ? 'border-emerald-500 text-emerald-300' : 'border-slate-700 text-slate-400'}`}
          >
            {s === '' ? 'All' : s === 'closed' ? 'Closed' : 'Open'}
          </button>
        ))}
        <span className="ml-auto text-slate-500">{data.total} trades</span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2">Entry (signal → fill)</th>
              <th className="px-3 py-2 text-right">Entry price</th>
              <th className="px-3 py-2">Exit (signal → fill)</th>
              <th className="px-3 py-2 text-right">Exit price</th>
              <th className="px-3 py-2 text-right">P&amp;L</th>
              <th className="px-3 py-2 text-right">P&amp;L %</th>
              <th className="px-3 py-2 text-right">Days</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {data.items.map((t) => (
              <tr key={t.id} className="hover:bg-slate-900/60">
                <td className="px-3 py-1.5">
                  <Link to={`/stocks/${t.symbol}`} className="font-medium text-slate-100 hover:text-emerald-400">
                    {t.symbol}
                  </Link>
                  {t.status === 'OPEN' && <span className="ml-2 text-xs text-sky-400">OPEN</span>}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{Number(t.quantity)}</td>
                <td className="px-3 py-1.5 whitespace-nowrap text-slate-400">
                  {t.entry_signal_date} → {t.entry_date}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(t.entry_price)}</td>
                <td className="px-3 py-1.5 whitespace-nowrap text-slate-400">
                  {t.exit_date ? `${t.exit_signal_date} → ${t.exit_date}` : '—'}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(t.exit_price)}</td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${changeClass(t.pnl)}`}>
                  {t.pnl == null ? '—' : fmtMoney(t.pnl)}
                </td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${changeClass(t.pnl_percent)}`}>
                  {formatPercent(t.pnl_percent)}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-400">{t.holding_days ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-xs text-slate-400">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
            className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
          </span>
          <button
            disabled={offset + PAGE >= data.total}
            onClick={() => setOffset(offset + PAGE)}
            className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}

function SkipsSection({ runId, summary }) {
  const [offset, setOffset] = useState(0)
  const [reason, setReason] = useState('')
  const [open, setOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['backtest-skips', runId, offset, reason],
    queryFn: () => getBacktestSkips(runId, { limit: PAGE, offset, reason: reason || undefined }),
    enabled: open,
    placeholderData: (prev) => prev,
  })
  const entries = Object.entries(summary ?? {}).sort((a, b) => b[1] - a[1])
  if (!entries.length) return <p className="text-sm text-slate-500">Every signal became a trade.</p>
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {entries.map(([key, count]) => (
          <button
            key={key}
            onClick={() => { setOpen(true); setReason(key === 'sell_no_position' ? '' : key); setOffset(0) }}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${reason === key ? 'border-emerald-500 text-emerald-300' : 'border-slate-700 text-slate-400 hover:border-slate-500'}`}
          >
            {key.replaceAll('_', ' ')}: <span className="tabular-nums">{count.toLocaleString()}</span>
          </button>
        ))}
        <button
          onClick={() => setOpen(!open)}
          className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:border-slate-500"
        >
          {open ? 'Hide detail' : 'Show detail'}
        </button>
      </div>
      <p className="text-xs text-slate-500">
        Sell signals for stocks never held are counted above but not listed row by row.
      </p>
      {open && data && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
              <tr>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2">Signal date</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Reason</th>
                <th className="px-3 py-2">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {data.items.map((s) => (
                <tr key={s.id}>
                  <td className="px-3 py-1.5 font-medium text-slate-200">{s.symbol}</td>
                  <td className="px-3 py-1.5 text-slate-400">{s.signal_date}</td>
                  <td className={`px-3 py-1.5 ${s.signal_type === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {s.signal_type}
                  </td>
                  <td className="px-3 py-1.5 text-slate-300">{s.reason.replaceAll('_', ' ')}</td>
                  <td className="px-3 py-1.5 text-slate-500">{s.detail ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.total > PAGE && (
            <div className="flex items-center justify-end gap-2 border-t border-slate-800 px-3 py-2 text-xs text-slate-400">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40">← Prev</button>
              <span>{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
              <button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40">Next →</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function BacktestDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: run, isPending, isError, error } = useQuery({
    queryKey: ['backtest', id],
    queryFn: () => getBacktest(id),
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'RUNNING' || s === 'PENDING' ? 2500 : false
    },
  })
  const remove = useMutation({
    mutationFn: () => deleteBacktest(id),
    onSuccess: () => navigate('/backtests'),
  })

  if (isPending) return <p className="text-sm text-slate-400">Loading backtest…</p>
  if (isError) return <p className="text-sm text-red-400">Failed to load: {error?.message}</p>

  const results = run.results_json
  const m = results?.metrics
  const equity = (results?.equity_curve ?? []).map(([time, value]) => ({ time, value }))
  const drawdown = (results?.equity_curve ?? []).map(([time, , dd]) => ({ time, value: dd }))
  const benchmark = (results?.benchmark_curve ?? []).map(([time, value]) => ({ time, value }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{run.name}</h1>
            <StatusBadge kind={STATUS_KIND[run.status] ?? 'degraded'}>{run.status}</StatusBadge>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            {run.start_date} → {run.end_date} · start {fmtMoney(run.initial_cash)} ·{' '}
            {run.settings_json?.max_open_positions} positions ×{' '}
            {run.settings_json?.position_size_percent}% · slippage{' '}
            {run.slippage_model_json?.value}% · commission ${run.commission_model_json?.amount}
            {run.settings_json?.benchmark_symbol
              ? ` · benchmark ${run.settings_json.benchmark_symbol}`
              : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/backtests" className="text-sm text-slate-400 hover:text-white">← All backtests</Link>
          <button
            onClick={() => { if (window.confirm(`Delete backtest "${run.name}"?`)) remove.mutate() }}
            disabled={run.status === 'RUNNING'}
            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:border-red-500 hover:text-red-400 disabled:opacity-40"
          >
            Delete
          </button>
        </div>
      </div>

      {(run.status === 'RUNNING' || run.status === 'PENDING') && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
          <p className="animate-pulse text-slate-300">Backtest running…</p>
          <p className="mt-1 text-sm text-slate-500">
            Simulating the full universe can take a few minutes. This page refreshes automatically.
          </p>
        </div>
      )}

      {run.status === 'FAILED' && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4">
          <p className="font-medium text-red-300">Backtest failed</p>
          <p className="mt-1 text-sm text-red-200/80">{run.error_message}</p>
        </div>
      )}

      {run.status === 'COMPLETED' && m && (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <MetricCard label="Final equity" value={fmtMoney(m.final_equity)} />
            <MetricCard label="Total return" value={formatPercent(m.total_return_pct)} cls={changeClass(m.total_return_pct)} />
            <MetricCard label="Annualized" value={formatPercent(m.annualized_return_pct)} cls={changeClass(m.annualized_return_pct)} />
            <MetricCard
              label={`Benchmark${run.settings_json?.benchmark_symbol ? ` (${run.settings_json.benchmark_symbol})` : ''}`}
              value={formatPercent(m.benchmark_return_pct)}
              cls={changeClass(m.benchmark_return_pct)}
            />
            <MetricCard label="Excess return" value={formatPercent(m.excess_return_pct)} cls={changeClass(m.excess_return_pct)} />
            <MetricCard label="Max drawdown" value={m.max_drawdown_pct == null ? '—' : `${m.max_drawdown_pct.toFixed(2)}%`} cls="text-red-400" />
            <MetricCard label="Sharpe" value={fmtRatio(m.sharpe_ratio)} />
            <MetricCard label="Sortino" value={fmtRatio(m.sortino_ratio)} />
            <MetricCard label="Volatility (ann.)" value={m.volatility_pct == null ? '—' : `${m.volatility_pct.toFixed(2)}%`} />
            <MetricCard label="Win rate" value={m.win_rate_pct == null ? '—' : `${m.win_rate_pct.toFixed(1)}%`} />
            <MetricCard label="Profit factor" value={fmtRatio(m.profit_factor)} />
            <MetricCard label="Trades (closed/open)" value={`${m.trades} / ${m.open_trades}`} />
            <MetricCard label="Avg winner" value={fmtMoney(m.average_winner)} cls="text-emerald-400" />
            <MetricCard label="Avg loser" value={fmtMoney(m.average_loser)} cls="text-red-400" />
            <MetricCard label="Largest winner" value={fmtMoney(m.largest_winner)} cls="text-emerald-400" />
            <MetricCard label="Largest loser" value={fmtMoney(m.largest_loser)} cls="text-red-400" />
            <MetricCard label="Avg holding (days)" value={m.average_holding_days ?? '—'} />
            <MetricCard label="Exposure / Turnover" value={`${m.exposure_pct?.toFixed(0) ?? '—'}% / ${fmtRatio(m.annual_turnover)}x`} />
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
                Open positions at end ({results.open_positions.length})
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
                        <td className="px-3 py-1.5 text-slate-400">{p.entry_date}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(p.entry_price)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(p.last_price)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{fmtMoney(p.market_value)}</td>
                        <td className={`px-3 py-1.5 text-right tabular-nums ${changeClass(p.unrealized_pnl)}`}>{fmtMoney(p.unrealized_pnl)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="space-y-2">
            <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
              Trades · {results.signals?.total?.toLocaleString()} signals → {results.signals?.executed_buys} buys, {results.signals?.executed_sells} sells
            </h2>
            <TradesTable runId={run.id} />
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Skipped signals</h2>
            <SkipsSection runId={run.id} summary={results.skip_summary} />
          </section>

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
      )}
    </div>
  )
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  deleteBacktest,
  getBacktest,
  getBacktestSkips,
  getBacktestTrades,
} from '../api/backtests.js'
import PerformanceReport from '../components/PerformanceReport.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { changeClass, formatMoney, formatPercent, formatPrice } from '../utils/format.js'

const STATUS_KIND = { COMPLETED: 'ok', RUNNING: 'degraded', PENDING: 'degraded', FAILED: 'down' }
const PAGE = 50

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
                  {t.pnl == null ? '—' : formatMoney(t.pnl)}
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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{run.name}</h1>
            <StatusBadge kind={STATUS_KIND[run.status] ?? 'degraded'}>{run.status}</StatusBadge>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            {run.start_date} → {run.end_date} · start {formatMoney(run.initial_cash)} ·{' '}
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

      {run.status === 'COMPLETED' && results?.metrics && (
        <>
          <PerformanceReport
            results={results}
            benchmarkSymbol={run.settings_json?.benchmark_symbol}
          />

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
        </>
      )}
    </div>
  )
}

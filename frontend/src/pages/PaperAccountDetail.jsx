import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  deletePaperAccount,
  getPaperAccount,
  getPaperOrders,
  getPaperPerformance,
  pausePaperAccount,
  processPaperAccount,
  resumePaperAccount,
} from '../api/paper.js'
import PerformanceReport from '../components/PerformanceReport.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { formatMoney, formatPrice } from '../utils/format.js'

const STATUS_KIND = { ACTIVE: 'ok', PAUSED: 'degraded', COMPLETED: 'degraded' }
const PAGE = 50
const ORDER_COLORS = {
  EXECUTED: 'text-emerald-400',
  PENDING: 'text-sky-400',
  REJECTED: 'text-amber-400',
  CANCELLED: 'text-slate-500',
}

function OrdersTable({ accountId }) {
  const [offset, setOffset] = useState(0)
  const [status, setStatus] = useState('')
  const { data } = useQuery({
    queryKey: ['paper-orders', accountId, offset, status],
    queryFn: () =>
      getPaperOrders(accountId, { limit: PAGE, offset, status: status || undefined }),
    placeholderData: (prev) => prev,
  })
  if (!data) return <p className="text-sm text-slate-400">Loading orders…</p>
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs">
        {['', 'executed', 'pending', 'rejected'].map((s) => (
          <button
            key={s || 'all'}
            onClick={() => { setStatus(s); setOffset(0) }}
            className={`rounded border px-2 py-0.5 capitalize ${status === s ? 'border-emerald-500 text-emerald-300' : 'border-slate-700 text-slate-400'}`}
          >
            {s === '' ? 'All' : s}
          </button>
        ))}
        <span className="ml-auto text-slate-500">{data.total} orders</span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
            <tr>
              <th className="px-3 py-2">Symbol</th>
              <th className="px-3 py-2">Side</th>
              <th className="px-3 py-2">Signal date</th>
              <th className="px-3 py-2">Filled</th>
              <th className="px-3 py-2 text-right">Qty</th>
              <th className="px-3 py-2 text-right">Fill price</th>
              <th className="px-3 py-2 text-right">Commission</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {data.items.map((o) => (
              <tr key={o.id} className="hover:bg-slate-900/60">
                <td className="px-3 py-1.5">
                  <Link to={`/stocks/${o.symbol}`} className="font-medium text-slate-100 hover:text-emerald-400">
                    {o.symbol}
                  </Link>
                </td>
                <td className={`px-3 py-1.5 ${o.side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>{o.side}</td>
                <td className="px-3 py-1.5 whitespace-nowrap text-slate-400">{o.signal_date}</td>
                <td className="px-3 py-1.5 whitespace-nowrap text-slate-400">{o.executed_at ?? '—'}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{o.quantity ?? '—'}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-300">{formatPrice(o.execution_price)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-slate-400">{o.commission ?? '—'}</td>
                <td className="px-3 py-1.5">
                  <span className={ORDER_COLORS[o.status] ?? 'text-slate-300'}>{o.status}</span>
                  {o.rejection_reason && (
                    <span className="ml-1 text-xs text-slate-500">({o.rejection_reason.replaceAll('_', ' ')})</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-xs text-slate-400">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40">← Prev</button>
          <span>{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
          <button disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="rounded border border-slate-700 px-2 py-1 disabled:opacity-40">Next →</button>
        </div>
      )}
    </div>
  )
}

export default function PaperAccountDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: account, isPending, isError, error } = useQuery({
    queryKey: ['paper-account', id],
    queryFn: () => getPaperAccount(id),
    // While the initial catch-up runs in the background there are no
    // snapshots yet — poll until they appear.
    refetchInterval: (query) =>
      query.state.data && query.state.data.last_snapshot_date == null ? 3000 : false,
  })
  const performance = useQuery({
    queryKey: ['paper-performance', id, account?.last_snapshot_date],
    queryFn: () => getPaperPerformance(id),
    enabled: account?.last_snapshot_date != null,
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['paper-account', id] })
    queryClient.invalidateQueries({ queryKey: ['paper-performance', id] })
    queryClient.invalidateQueries({ queryKey: ['paper-orders', id] })
  }
  const pauseResume = useMutation({
    mutationFn: () =>
      account.status === 'ACTIVE' ? pausePaperAccount(id) : resumePaperAccount(id),
    onSuccess: refresh,
  })
  const processNow = useMutation({ mutationFn: () => processPaperAccount(id), onSuccess: refresh })
  const remove = useMutation({
    mutationFn: () => deletePaperAccount(id),
    onSuccess: () => navigate('/paper-accounts'),
  })

  if (isPending) return <p className="text-sm text-slate-400">Loading account…</p>
  if (isError) return <p className="text-sm text-red-400">Failed to load: {error?.message}</p>

  const params = account.strategy_parameter_snapshot_json ?? {}
  const settings = account.settings_json ?? {}

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">{account.name}</h1>
            <StatusBadge kind={STATUS_KIND[account.status] ?? 'degraded'}>{account.status}</StatusBadge>
          </div>
          <p className="mt-1 text-sm text-slate-400">
            Started {account.start_date} with {formatMoney(account.initial_cash)} ·{' '}
            {settings.maximum_open_positions} positions × {settings.position_size_percent}% ·
            slippage {settings.slippage_percent}% · commission ${settings.commission_per_trade} ·
            vol×{params.volume_multiplier} · as of {account.last_snapshot_date ?? '(catching up…)'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/paper-accounts" className="text-sm text-slate-400 hover:text-white">← All accounts</Link>
          <button
            onClick={() => processNow.mutate()}
            disabled={processNow.isPending || account.status !== 'ACTIVE'}
            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
          >
            {processNow.isPending ? 'Processing…' : 'Process now'}
          </button>
          <button
            onClick={() => pauseResume.mutate()}
            disabled={pauseResume.isPending}
            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:border-slate-500 disabled:opacity-40"
          >
            {account.status === 'ACTIVE' ? 'Pause' : 'Resume'}
          </button>
          <button
            onClick={() => {
              if (window.confirm(`Delete paper account "${account.name}" and all its history?`)) {
                remove.mutate()
              }
            }}
            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-400 hover:border-red-500 hover:text-red-400"
          >
            Delete
          </button>
        </div>
      </div>

      {account.last_snapshot_date == null && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
          <p className="animate-pulse text-slate-300">Catching up from {account.start_date}…</p>
          <p className="mt-1 text-sm text-slate-500">
            The account replays signals from its start date to today. This page refreshes
            automatically.
          </p>
        </div>
      )}

      {performance.data?.metrics && (
        <PerformanceReport
          results={performance.data}
          benchmarkSymbol={settings.benchmark_symbol}
        />
      )}
      {performance.data && !performance.data.metrics && (
        <p className="text-sm text-slate-400">{performance.data.notes?.[0]}</p>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Orders</h2>
        <OrdersTable accountId={account.id} />
      </section>
    </div>
  )
}

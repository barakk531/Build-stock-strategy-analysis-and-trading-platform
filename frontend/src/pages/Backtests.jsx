import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { deleteBacktest, listBacktests } from '../api/backtests.js'
import StatusBadge from '../components/StatusBadge.jsx'
import { changeClass, formatPercent } from '../utils/format.js'

const STATUS_KIND = { COMPLETED: 'ok', RUNNING: 'degraded', PENDING: 'degraded', FAILED: 'down' }

export default function Backtests() {
  const queryClient = useQueryClient()
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['backtests'],
    queryFn: () => listBacktests({ limit: 100 }),
    // Keep polling while anything is still running.
    refetchInterval: (query) =>
      query.state.data?.items?.some((r) => r.status === 'RUNNING' || r.status === 'PENDING')
        ? 3000
        : false,
  })

  const remove = useMutation({
    mutationFn: deleteBacktest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backtests'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Backtests</h1>
        <Link
          to="/backtests/new"
          className="rounded bg-emerald-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-emerald-400"
        >
          New backtest
        </Link>
      </div>

      <p className="text-xs text-slate-500">
        Universe is the <span className="text-slate-300">current</span> S&amp;P 500 projected into
        the past (survivorship bias — results are optimistic). Fills: next market open, adjusted
        for splits.
      </p>

      {isPending && <p className="text-sm text-slate-400">Loading backtests…</p>}
      {isError && <p className="text-sm text-red-400">Failed to load: {error?.message}</p>}

      {data && data.items.length === 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
          <p className="text-slate-400">No backtests yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Run your first one to see how the strategy would have performed.
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full min-w-[900px] text-sm">
            <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Period</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Total return</th>
                <th className="px-3 py-2 text-right">Max drawdown</th>
                <th className="px-3 py-2 text-right">Trades</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {data.items.map((run) => (
                <tr key={run.id} className="hover:bg-slate-900/60">
                  <td className="px-3 py-2">
                    <Link to={`/backtests/${run.id}`} className="font-medium text-slate-100 hover:text-emerald-400">
                      {run.name}
                    </Link>
                    {run.error_message && (
                      <p className="mt-0.5 max-w-96 truncate text-xs text-red-400">{run.error_message}</p>
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-slate-400">
                    {run.start_date} → {run.end_date}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge kind={STATUS_KIND[run.status] ?? 'degraded'}>{run.status}</StatusBadge>
                  </td>
                  <td className={`px-3 py-2 text-right tabular-nums ${changeClass(run.total_return_pct)}`}>
                    {formatPercent(run.total_return_pct)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-red-400">
                    {run.max_drawdown_pct == null ? '—' : `${run.max_drawdown_pct.toFixed(2)}%`}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-300">
                    {run.trades_count ?? '—'}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-slate-500">
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete backtest "${run.name}"?`)) remove.mutate(run.id)
                      }}
                      disabled={run.status === 'RUNNING' || remove.isPending}
                      className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:border-red-500 hover:text-red-400 disabled:opacity-40"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

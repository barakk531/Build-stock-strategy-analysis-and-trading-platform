import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { deletePaperAccount, listPaperAccounts } from '../api/paper.js'
import StatusBadge from '../components/StatusBadge.jsx'
import { changeClass, formatMoney, formatPercent } from '../utils/format.js'

const STATUS_KIND = { ACTIVE: 'ok', PAUSED: 'degraded', COMPLETED: 'degraded' }

export default function PaperAccounts() {
  const queryClient = useQueryClient()
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['paper-accounts'],
    queryFn: listPaperAccounts,
    refetchInterval: 60_000,
  })
  const remove = useMutation({
    mutationFn: deletePaperAccount,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['paper-accounts'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Paper Accounts</h1>
        <Link
          to="/paper-accounts/new"
          className="rounded bg-emerald-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-emerald-400"
        >
          New account
        </Link>
      </div>

      <p className="text-xs text-slate-500">
        Simulated accounts trade automatically on their strategy's signals: fills at the next
        trading day's open with slippage and commission, splits and dividends applied. No real
        money is involved.
      </p>

      {isPending && <p className="text-sm text-slate-400">Loading accounts…</p>}
      {isError && <p className="text-sm text-red-400">Failed to load: {error?.message}</p>}

      {data && data.items.length === 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
          <p className="text-slate-400">No paper accounts yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Create one to trade the strategy automatically with simulated money — including a
            catch-up from any past start date.
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full min-w-[880px] text-sm">
            <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Equity</th>
                <th className="px-3 py-2 text-right">Total return</th>
                <th className="px-3 py-2 text-right">Cash</th>
                <th className="px-3 py-2 text-right">Positions</th>
                <th className="px-3 py-2 text-right">Pending</th>
                <th className="px-3 py-2">Started</th>
                <th className="px-3 py-2">As of</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {data.items.map((a) => (
                <tr key={a.id} className="hover:bg-slate-900/60">
                  <td className="px-3 py-2">
                    <Link to={`/paper-accounts/${a.id}`} className="font-medium text-slate-100 hover:text-emerald-400">
                      {a.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge kind={STATUS_KIND[a.status] ?? 'degraded'}>{a.status}</StatusBadge>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-100">{formatMoney(a.total_equity)}</td>
                  <td className={`px-3 py-2 text-right tabular-nums ${changeClass(a.total_return_pct)}`}>
                    {formatPercent(a.total_return_pct)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-400">{formatMoney(a.cash_balance)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-300">{a.open_positions}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-400">{a.pending_orders}</td>
                  <td className="px-3 py-2 whitespace-nowrap text-slate-500">{a.start_date}</td>
                  <td className="px-3 py-2 whitespace-nowrap text-slate-500">{a.last_snapshot_date ?? '—'}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => {
                        if (window.confirm(`Delete paper account "${a.name}" and all its history?`)) {
                          remove.mutate(a.id)
                        }
                      }}
                      disabled={remove.isPending}
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

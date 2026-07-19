import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { actions, getDataHealth, getHealthReport, getJobs } from '../api/admin.js'
import StatusBadge from '../components/StatusBadge.jsx'

function Card({ label, value, warn }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${warn ? 'text-amber-400' : 'text-slate-100'}`}>
        {value ?? '—'}
      </p>
    </div>
  )
}

const ACTION_BUTTONS = [
  { key: 'syncPrices', label: 'Sync prices', hint: 'Incremental daily download' },
  { key: 'recalcIndicators', label: 'Recalculate indicators', hint: 'SMA/volume/slope' },
  { key: 'scanSignals', label: 'Scan signals', hint: 'Detect new BUY/SELL events' },
  { key: 'telegramQueue', label: 'Queue alerts', hint: "Latest day's signals" },
  { key: 'telegramProcess', label: 'Send alerts', hint: 'Process pending queue' },
  { key: 'paperProcess', label: 'Process paper accounts', hint: 'Orders + snapshots' },
  { key: 'syncUniverse', label: 'Sync S&P 500 universe', hint: 'Weekly membership' },
  { key: 'telegramTest', label: 'Telegram test message', hint: 'Verify bot config' },
]

export default function AdminData() {
  const queryClient = useQueryClient()
  const health = useQuery({ queryKey: ['data-health'], queryFn: getDataHealth })
  const report = useQuery({ queryKey: ['health-report'], queryFn: getHealthReport })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: getJobs, refetchInterval: 60_000 })
  const [log, setLog] = useState([])

  const run = useMutation({
    mutationFn: async ({ key }) => {
      const { data } = await actions[key]()
      return { key, data }
    },
    onSuccess: ({ key, data }) => {
      setLog((l) => [{ key, at: new Date(), result: data }, ...l].slice(0, 8))
      queryClient.invalidateQueries({ queryKey: ['data-health'] })
      queryClient.invalidateQueries({ queryKey: ['health-report'] })
    },
    onError: (err, { key }) =>
      setLog((l) =>
        [{ key, at: new Date(), error: err.response?.data?.detail ?? err.message }, ...l].slice(0, 8),
      ),
  })

  const h = health.data
  const r = report.data
  const authError = [health, report, jobs].some((q) => q.error?.response?.status === 401)

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Data Administration</h1>

      {authError && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
          The server requires an API key — enter it on the Settings page.
        </p>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Data health</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Card label="Active stocks" value={h?.active_stocks} />
          <Card label="With prices" value={h?.stocks_with_prices} warn={h && h.stocks_with_prices < h.active_stocks} />
          <Card label="Price rows" value={h?.total_price_rows?.toLocaleString()} />
          <Card label="Latest trade date" value={h?.latest_trade_date} />
          <Card label="Stale (>5d)" value={h?.stale_prices} warn={h?.stale_prices > 0} />
          <Card label="Never synced" value={h?.never_synced} warn={h?.never_synced > 0} />
          <Card label="Latest indicators" value={r?.latest_indicator_date} warn={r?.indicators_behind_prices} />
          <Card label="Latest signals" value={r?.latest_signal_date} />
          <Card label="Duplicate price rows" value={r?.duplicate_price_rows} warn={r?.duplicate_price_rows > 0} />
          <Card label="Stuck paper orders" value={r?.paper_orders_stuck} warn={r?.paper_orders_stuck > 0} />
          <Card label="Active accounts" value={r?.active_paper_accounts} />
          <Card
            label="Telegram (sent / pending / failed)"
            value={
              r
                ? `${r.telegram_alerts?.SENT ?? 0} / ${r.telegram_alerts?.PENDING ?? 0} / ${r.telegram_alerts?.FAILED ?? 0}`
                : '—'
            }
            warn={(r?.telegram_alerts?.FAILED ?? 0) > 0}
          />
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
          Scheduled jobs{' '}
          {jobs.data && (
            <StatusBadge kind={jobs.data.scheduler_running ? 'ok' : 'down'}>
              {jobs.data.scheduler_running ? 'scheduler running' : 'scheduler stopped'}
            </StatusBadge>
          )}
        </h2>
        <div className="overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
              <tr>
                <th className="px-3 py-2">Job</th>
                <th className="px-3 py-2">Schedule</th>
                <th className="px-3 py-2">Next run</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {(jobs.data?.jobs ?? []).map((job) => (
                <tr key={job.id}>
                  <td className="px-3 py-1.5 font-medium text-slate-200">{job.id.replaceAll('_', ' ')}</td>
                  <td className="px-3 py-1.5 text-slate-400">{job.trigger}</td>
                  <td className="px-3 py-1.5 text-slate-300">
                    {job.next_run_time ? new Date(job.next_run_time).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
              {jobs.data?.jobs?.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-3 py-2 text-slate-500">
                    No jobs registered (scheduler disabled).
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Manual actions</h2>
        <p className="text-xs text-slate-500">
          Every action is idempotent — rerunning never duplicates data. The nightly job runs
          these in order automatically.
        </p>
        <div className="flex flex-wrap gap-2">
          {ACTION_BUTTONS.map(({ key, label, hint }) => (
            <button
              key={key}
              title={hint}
              disabled={run.isPending}
              onClick={() => run.mutate({ key })}
              className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
            >
              {run.isPending && run.variables?.key === key ? 'Running…' : label}
            </button>
          ))}
        </div>
        {log.length > 0 && (
          <div className="space-y-1 rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-xs">
            {log.map((entry, i) => (
              <p key={i} className={entry.error ? 'text-red-400' : 'text-slate-400'}>
                [{entry.at.toLocaleTimeString()}] {entry.key}:{' '}
                {entry.error ?? JSON.stringify(entry.result).slice(0, 220)}
              </p>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

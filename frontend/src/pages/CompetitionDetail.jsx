import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { cloneAccount, getLeaderboard } from '../api/competitions.js'
import MultiEquityChart from '../charts/MultiEquityChart.jsx'
import { SERIES_COLORS } from '../utils/colors.js'
import { changeClass, formatMoney, formatPercent, formatRatio } from '../utils/format.js'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function FairnessPanel({ fairness }) {
  if (!fairness) return null
  return (
    <section className={`rounded-lg border p-4 ${fairness.fair ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-amber-500/40 bg-amber-500/5'}`}>
      <h2 className={`text-xs font-medium tracking-wide uppercase ${fairness.fair ? 'text-emerald-400' : 'text-amber-400'}`}>
        {fairness.fair ? '✓ Fair comparison — all assumptions match' : '⚠ Comparison caveats — assumptions differ'}
      </h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {fairness.checks.map((check) => (
          <span
            key={check.key}
            title={Object.entries(check.values).map(([k, v]) => `${k}: ${v ?? '—'}`).join('\n')}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${
              check.fair ? 'border-slate-700 text-slate-400' : 'border-amber-500 text-amber-300'
            }`}
          >
            {check.fair ? '✓' : '✗'} {check.label}
          </span>
        ))}
      </div>
    </section>
  )
}

function MonthlyComparison({ monthly }) {
  const accounts = Object.keys(monthly ?? {})
  if (!accounts.length) return null
  const keys = new Set()
  for (const list of Object.values(monthly)) {
    for (const { year, month } of list) keys.add(`${year}-${String(month).padStart(2, '0')}`)
  }
  const periods = [...keys].sort()
  const lookup = {}
  for (const [account, list] of Object.entries(monthly)) {
    lookup[account] = Object.fromEntries(
      list.map((m) => [`${m.year}-${String(m.month).padStart(2, '0')}`, m.return_pct]),
    )
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full min-w-[640px] text-xs">
        <thead className="bg-slate-900 text-slate-400 uppercase">
          <tr>
            <th className="px-2 py-1.5 text-left">Month</th>
            {accounts.map((a) => (
              <th key={a} className="px-2 py-1.5 text-right">{a}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {periods.map((p) => {
            const [year, month] = p.split('-')
            return (
              <tr key={p}>
                <td className="px-2 py-1.5 text-slate-300">{MONTHS[Number(month) - 1]} {year}</td>
                {accounts.map((a) => {
                  const v = lookup[a][p]
                  return (
                    <td key={a} className={`px-2 py-1.5 text-right tabular-nums ${changeClass(v)}`}>
                      {v == null ? '·' : `${v.toFixed(1)}%`}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function CompetitionDetail() {
  const { id } = useParams()
  const queryClient = useQueryClient()
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['leaderboard', id],
    queryFn: () => getLeaderboard(id),
    refetchInterval: 120_000,
  })
  const clone = useMutation({
    mutationFn: ({ accountId }) => cloneAccount(accountId, { competition_id: Number(id) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['leaderboard', id] }),
  })

  if (isPending) return <p className="text-sm text-slate-400">Loading leaderboard…</p>
  if (isError) return <p className="text-sm text-red-400">Failed to load: {error?.message}</p>

  const rows = data.leaderboard ?? []
  // The S&P competitor is a ranked table row; the chart already draws it as the
  // gray "Benchmark" line, so keep it out of the colored per-account series.
  const accountNames = rows.filter((r) => r.metrics && !r.is_benchmark).map((r) => r.account_name)
  const colorOf = Object.fromEntries(
    accountNames.map((name, i) => [name, SERIES_COLORS[i % SERIES_COLORS.length]]),
  )
  const equitySeries = accountNames.map((name) => ({
    name,
    points: (data.equity_curves[name] ?? []).map(([time, value]) => ({ time, value })),
  }))
  const drawdownSeries = accountNames.map((name) => ({
    name,
    points: (data.drawdown_curves[name] ?? []).map(([time, value]) => ({ time, value })),
  }))
  const benchmark = (data.benchmark_curve ?? []).map(([time, value]) => ({ time, value }))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{data.competition.name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {data.competition.description ? `${data.competition.description} · ` : ''}
            window {data.window.start ?? '—'} → {data.window.end ?? '—'}
            {data.benchmark_symbol ? ` · benchmark ${data.benchmark_symbol}` : ''}
          </p>
        </div>
        <Link to="/competitions" className="text-sm text-slate-400 hover:text-white">
          ← All competitions
        </Link>
      </div>

      <FairnessPanel fairness={data.fairness} />

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full min-w-[1100px] text-sm">
          <thead className="bg-slate-900 text-left text-xs text-slate-400 uppercase">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Account</th>
              <th className="px-3 py-2">Strategy / parameters</th>
              <th className="px-3 py-2 text-right">Return</th>
              <th className="px-3 py-2 text-right">Annualized</th>
              <th className="px-3 py-2 text-right">Alpha</th>
              <th className="px-3 py-2 text-right">Max DD</th>
              <th className="px-3 py-2 text-right">Sharpe</th>
              <th className="px-3 py-2 text-right">Win rate</th>
              <th className="px-3 py-2 text-right">PF</th>
              <th className="px-3 py-2 text-right">Trades</th>
              <th className="px-3 py-2 text-right">Cash</th>
              <th className="px-3 py-2 text-right">Exposure</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {rows.map((row) => {
              const m = row.metrics
              const vs = row.vs_benchmark_pct
              return (
                <tr
                  key={row.account_id ?? row.account_name}
                  className={row.is_benchmark
                    ? 'border-l-2 border-amber-400/70 bg-amber-500/5'
                    : 'hover:bg-slate-900/60'}
                >
                  <td className="px-3 py-2 font-semibold text-slate-300">{row.rank ?? '—'}</td>
                  <td className="px-3 py-2">
                    {row.is_benchmark ? (
                      <span className="font-medium text-amber-300">
                        {row.account_name}
                        <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] tracking-wide text-amber-400 uppercase">
                          the line to beat
                        </span>
                      </span>
                    ) : (
                      <>
                        <span
                          className="mr-2 inline-block h-2 w-2 rounded-full"
                          style={{ background: colorOf[row.account_name] ?? '#475569' }}
                        />
                        <Link to={`/paper-accounts/${row.account_id}`} className="font-medium text-slate-100 hover:text-emerald-400">
                          {row.account_name}
                        </Link>
                        {row.account_status !== 'ACTIVE' && (
                          <span className="ml-2 text-xs text-slate-500">{row.account_status}</span>
                        )}
                        {vs != null && (
                          <span
                            title={`Days beating index: ${row.pct_days_outperforming ?? '—'}% · Info ratio: ${row.information_ratio ?? '—'} · Up/down capture: ${row.up_capture_pct ?? '—'}% / ${row.down_capture_pct ?? '—'}%`}
                            className={`ml-2 rounded px-1.5 py-0.5 text-[10px] ${row.beats_benchmark ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}
                          >
                            {row.beats_benchmark ? '▲ beating' : '▼ trailing'} S&P {formatPercent(vs)}
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-400">
                    {row.strategy_name}
                    <br />
                    {row.parameter_summary}
                  </td>
                  {m ? (
                    <>
                      <td className={`px-3 py-2 text-right tabular-nums ${changeClass(m.total_return_pct)}`}>{formatPercent(m.total_return_pct)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums ${changeClass(m.annualized_return_pct)}`}>{formatPercent(m.annualized_return_pct)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums ${changeClass(row.alpha_pct)}`}>{formatPercent(row.alpha_pct)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-red-400">{m.max_drawdown_pct?.toFixed(1)}%</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-200">{formatRatio(m.sharpe_ratio)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-300">{m.win_rate_pct == null ? '—' : `${m.win_rate_pct.toFixed(0)}%`}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-300">{formatRatio(m.profit_factor)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-300">{m.trades}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-400">{formatMoney(row.current_cash)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-slate-300">{row.current_exposure_pct?.toFixed(0)}%</td>
                    </>
                  ) : (
                    <td colSpan={10} className="px-3 py-2 text-slate-500">
                      No processed data in the common window yet.
                    </td>
                  )}
                  <td className="px-3 py-2 text-right">
                    {!row.is_benchmark && (
                      <button
                        onClick={() => clone.mutate({ accountId: row.account_id })}
                        disabled={clone.isPending}
                        title="Clone this configuration into a new account in this competition"
                        className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-40"
                      >
                        Clone
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {equitySeries.length > 0 && (
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
            {accountNames.map((name) => (
              <span key={name}>
                <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: colorOf[name] }} />
                {name}
              </span>
            ))}
            {benchmark.length > 0 && (
              <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-slate-400" />Benchmark</span>
            )}
            <span className="ml-auto text-slate-500">Rebased to 100 · lower pane: drawdown %</span>
          </div>
          <div className="mt-2">
            <MultiEquityChart series={equitySeries} drawdowns={drawdownSeries} benchmark={benchmark} />
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Monthly returns comparison (%)</h2>
        <MonthlyComparison monthly={data.monthly_returns} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {Object.keys(data.best_worst_trades ?? {}).length > 0 && (
          <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Best &amp; worst trades</h2>
            <div className="mt-2 space-y-2 text-sm">
              {Object.entries(data.best_worst_trades).map(([account, bw]) => (
                <div key={account} className="flex flex-wrap items-center gap-2">
                  <span className="w-40 truncate text-slate-300">{account}</span>
                  <span className="text-emerald-400 tabular-nums">
                    ▲ {bw.best.symbol} {formatMoney(bw.best.pnl)}
                  </span>
                  <span className="text-red-400 tabular-nums">
                    ▼ {bw.worst.symbol} {formatMoney(bw.worst.pnl)}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {Object.keys(data.holdings ?? {}).length > 0 && (
          <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Current holdings</h2>
            <div className="mt-2 space-y-2 text-sm">
              {Object.entries(data.holdings).map(([account, positions]) => (
                <div key={account} className="flex flex-wrap items-baseline gap-1.5">
                  <span className="w-40 truncate text-slate-300">{account}</span>
                  {positions.length === 0 && <span className="text-slate-500">all cash</span>}
                  {positions.map((p) => (
                    <Link
                      key={p.symbol}
                      to={`/stocks/${p.symbol}`}
                      title={`value ${formatMoney(p.market_value)} · unrealized ${formatMoney(p.unrealized_pnl)}`}
                      className={`rounded border border-slate-700 px-1.5 py-0.5 text-xs hover:border-slate-500 ${changeClass(p.unrealized_pnl)}`}
                    >
                      {p.symbol}
                    </Link>
                  ))}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {data.notes?.length > 0 && (
        <section className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
          <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
            {data.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getScanner } from '../api/scanner.js'
import StatusBadge from '../components/StatusBadge.jsx'
import { useHealth } from '../hooks/useHealth.js'

function useMarketPulse() {
  return useQuery({
    queryKey: ['market-pulse'],
    queryFn: async () => {
      const [all, buys, sells] = await Promise.all([
        getScanner({ limit: 1 }),
        getScanner({ limit: 5, buy_state: true, sort: 'volume_ratio', order: 'desc' }),
        getScanner({ limit: 1, sell_state: true }),
      ])
      return { tracked: all.total, buys: buys.total, sells: sells.total, top: buys.items }
    },
    refetchInterval: 120_000,
  })
}

export default function Dashboard() {
  const { data, isPending, isError, error, refetch, isFetching } = useHealth()
  const pulse = useMarketPulse()

  const tiles = [
    { label: 'Tracked stocks', value: pulse.data?.tracked, to: '/scanner' },
    { label: 'In buy state now', value: pulse.data?.buys, to: '/scanner?buy_state=1', cls: 'text-emerald-400' },
    { label: 'In sell state now', value: pulse.data?.sells, to: '/scanner?sell_state=1', cls: 'text-red-400' },
    { label: 'Active paper accounts', value: null, phase: 7 },
  ]

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
            System status
          </h2>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            {isFetching ? 'Checking…' : 'Refresh'}
          </button>
        </div>

        {isPending && <p className="mt-4 text-sm text-slate-400">Contacting backend…</p>}

        {isError && (
          <div className="mt-4 space-y-2">
            <StatusBadge kind="down">Backend unreachable</StatusBadge>
            <p className="text-sm text-slate-400">
              {error?.message}. Is the API running on port 8000?
            </p>
          </div>
        )}

        {data && (
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-slate-500">Backend</dt>
              <dd className="mt-1">
                <StatusBadge kind={data.status === 'ok' ? 'ok' : 'degraded'}>
                  {data.status}
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Database</dt>
              <dd className="mt-1">
                <StatusBadge kind={data.database === 'ok' ? 'ok' : 'down'}>
                  {data.database}
                </StatusBadge>
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Version</dt>
              <dd className="mt-1 text-sm text-slate-200">
                {data.version} ({data.environment})
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Checked at</dt>
              <dd className="mt-1 text-sm text-slate-200">
                {new Date(data.timestamp).toLocaleTimeString()}
              </dd>
            </div>
          </dl>
        )}
      </section>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map(({ label, value, to, cls, phase }) => {
          const body = (
            <>
              <p className="text-xs text-slate-500">{label}</p>
              <p className={`mt-2 text-2xl font-semibold tabular-nums ${cls ?? 'text-slate-100'}`}>
                {value ?? '—'}
              </p>
              {phase && <p className="mt-1 text-xs text-slate-600">arrives in Phase {phase}</p>}
            </>
          )
          return to ? (
            <Link key={label} to={to} className="rounded-lg border border-slate-800 bg-slate-900 p-4 hover:border-slate-700">
              {body}
            </Link>
          ) : (
            <div key={label} className="rounded-lg border border-slate-800 bg-slate-900 p-4">{body}</div>
          )
        })}
      </section>

      {pulse.data?.top?.length > 0 && (
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
            Buy states by volume ratio
          </h2>
          <div className="mt-2 divide-y divide-slate-800/60">
            {pulse.data.top.map((r) => (
              <Link
                key={r.symbol}
                to={`/stocks/${r.symbol}`}
                className="flex items-center justify-between py-2 text-sm hover:bg-slate-800/40"
              >
                <span className="font-medium text-slate-100">{r.symbol}</span>
                <span className="max-w-56 truncate text-slate-400">{r.company_name}</span>
                <span className="tabular-nums text-emerald-400">{r.volume_ratio?.toFixed(2)}x vol</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

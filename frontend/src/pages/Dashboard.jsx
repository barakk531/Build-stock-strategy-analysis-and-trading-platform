import StatusBadge from '../components/StatusBadge.jsx'
import { useHealth } from '../hooks/useHealth.js'

const upcomingTiles = [
  { label: 'Tracked stocks', phase: 2 },
  { label: 'Current buy signals', phase: 3 },
  { label: 'Current sell signals', phase: 3 },
  { label: 'Active paper accounts', phase: 7 },
]

export default function Dashboard() {
  const { data, isPending, isError, error, refetch, isFetching } = useHealth()

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
        {upcomingTiles.map(({ label, phase }) => (
          <div key={label} className="rounded-lg border border-slate-800 bg-slate-900 p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-2 text-2xl font-semibold text-slate-600">—</p>
            <p className="mt-1 text-xs text-slate-600">arrives in Phase {phase}</p>
          </div>
        ))}
      </section>
    </div>
  )
}

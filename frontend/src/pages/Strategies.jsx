import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { evaluateStrategy, listStrategies } from '../api/strategies.js'
import StatusBadge from '../components/StatusBadge.jsx'
import { formatCompact, formatPrice } from '../utils/format.js'

function Condition({ c }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 text-sm">
      <span className="flex items-center gap-2">
        <span className={c.passed ? 'text-emerald-400' : 'text-red-400'}>{c.passed ? '✓' : '✗'}</span>
        <span className="text-slate-300">{c.label}</span>
      </span>
      <span className="text-xs text-slate-400 tabular-nums">
        {c.actual == null ? '—' : formatCompact(c.actual)} {c.comparison}{' '}
        {c.threshold == null ? '—' : formatCompact(c.threshold)}
      </span>
    </div>
  )
}

export default function Strategies() {
  const [selectedId, setSelectedId] = useState(null)
  const [symbol, setSymbol] = useState('AAPL')
  const [edited, setEdited] = useState({})

  const { data: strategies, isPending, isError, error } = useQuery({
    queryKey: ['strategies'],
    queryFn: listStrategies,
  })

  const selected = useMemo(() => {
    if (!strategies?.length) return null
    return strategies.find((s) => s.id === selectedId) ?? strategies[0]
  }, [strategies, selectedId])

  // Reset the editable parameter copy whenever the selected strategy changes.
  useEffect(() => {
    if (selected) setEdited({ ...selected.parameters_json })
  }, [selected?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const evaluate = useMutation({
    mutationFn: ({ id, payload }) => evaluateStrategy(id, payload),
  })

  function runEvaluate() {
    if (!selected || !symbol.trim()) return
    const parameters = Object.fromEntries(
      Object.entries(edited).filter(([, v]) => v !== null && v !== ''),
    )
    evaluate.mutate({ id: selected.id, payload: { symbol: symbol.trim().toUpperCase(), parameters } })
  }

  function setParam(key, value) {
    setEdited((prev) => ({ ...prev, [key]: value }))
  }

  if (isPending) return <p className="text-sm text-slate-400">Loading strategies…</p>
  if (isError) return <p className="text-sm text-red-400">Failed to load strategies: {error?.message}</p>
  if (!strategies?.length) return <p className="text-sm text-slate-400">No strategies defined yet.</p>

  const events = evaluate.data?.events ?? []

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Strategies</h1>

      <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
        {/* Strategy list */}
        <aside className="space-y-1">
          {strategies.map((s) => (
            <button
              key={s.id}
              onClick={() => setSelectedId(s.id)}
              className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                selected?.id === s.id
                  ? 'border-emerald-500/40 bg-slate-800 text-slate-100'
                  : 'border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700'
              }`}
            >
              <span className="font-medium">{s.name}</span>
              <span className="mt-0.5 block text-xs text-slate-500">
                {s.strategy_type} · v{s.version}
              </span>
            </button>
          ))}
        </aside>

        {/* Selected strategy */}
        {selected && (
          <div className="space-y-4">
            <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold">{selected.name}</h2>
                <span className="text-xs text-slate-500">
                  {selected.strategy_type} · version {selected.version}
                </span>
                <StatusBadge kind={selected.is_active ? 'ok' : 'loading'}>
                  {selected.is_active ? 'Active' : 'Inactive'}
                </StatusBadge>
              </div>
              {selected.description && (
                <p className="mt-2 text-sm text-slate-400">{selected.description}</p>
              )}
            </section>

            {/* Evaluate (what-if) */}
            <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
              <h3 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
                Evaluate on a symbol
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                Run this strategy on one stock with temporary parameter overrides. Nothing is saved —
                this is a what-if against stored price history.
              </p>

              <div className="mt-3 flex flex-wrap items-end gap-2">
                <label className="text-xs text-slate-400">
                  Symbol
                  <input
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                    className="mt-1 block w-32 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
                  />
                </label>
                <button
                  onClick={runEvaluate}
                  disabled={evaluate.isPending || !symbol.trim()}
                  className="rounded bg-emerald-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:opacity-40"
                >
                  {evaluate.isPending ? 'Evaluating…' : 'Evaluate'}
                </button>
                <button
                  onClick={() => setEdited({ ...selected.parameters_json })}
                  className="rounded border border-slate-700 px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200"
                >
                  Reset parameters
                </button>
              </div>

              {/* Editable parameters */}
              <div className="mt-4 grid gap-x-4 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(edited).map(([key, value]) => {
                  const original = selected.parameters_json[key]
                  const isNumber = typeof original === 'number'
                  const isBool = typeof original === 'boolean'
                  return (
                    <label key={key} className="text-xs text-slate-400">
                      {key}
                      {isBool ? (
                        <input
                          type="checkbox"
                          checked={Boolean(value)}
                          onChange={(e) => setParam(key, e.target.checked)}
                          className="ml-2 accent-emerald-500 align-middle"
                        />
                      ) : (
                        <input
                          type={isNumber ? 'number' : 'text'}
                          step="any"
                          value={value ?? ''}
                          placeholder={original == null ? 'unset' : ''}
                          onChange={(e) => {
                            const raw = e.target.value
                            setParam(key, isNumber ? (raw === '' ? '' : Number(raw)) : raw)
                          }}
                          className="mt-1 block w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
                        />
                      )}
                    </label>
                  )
                })}
              </div>
            </section>

            {/* Results */}
            {evaluate.isError && (
              <p className="text-sm text-red-400">
                Evaluation failed: {evaluate.error?.response?.data?.detail
                  ? typeof evaluate.error.response.data.detail === 'string'
                    ? evaluate.error.response.data.detail
                    : 'invalid parameters'
                  : evaluate.error?.message}
              </p>
            )}
            {evaluate.data && (
              <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
                    {evaluate.data.symbol} — {events.length} signal event
                    {events.length === 1 ? '' : 's'}
                  </h3>
                </div>
                {events.length === 0 && (
                  <p className="mt-2 text-sm text-slate-400">
                    No transition events for {evaluate.data.symbol} under these parameters.
                  </p>
                )}
                <div className="mt-3 space-y-3">
                  {[...events].reverse().map((event, i) => (
                    <div
                      key={`${event.trade_date}-${i}`}
                      className="rounded border border-slate-800 bg-slate-950/50 p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <StatusBadge kind={event.signal_type === 'SELL' ? 'down' : 'ok'}>
                          {event.signal_type}
                        </StatusBadge>
                        <span className="text-slate-300">{event.trade_date}</span>
                        <span className="text-slate-500">ref {formatPrice(event.reference_price)}</span>
                        <span className="text-xs text-slate-500">
                          exec {event.execution_date ?? 'next open'}
                        </span>
                      </div>
                      <div className="mt-2 divide-y divide-slate-800/60">
                        {event.conditions.map((c) => (
                          <Condition key={c.key} c={c} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

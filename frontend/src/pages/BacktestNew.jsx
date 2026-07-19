import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createBacktest, listStrategies } from '../api/backtests.js'
import { getScanner } from '../api/scanner.js'

// The spec's five market-cap bands, reused as universe presets.
const CAP_PRESETS = [
  { label: 'Any cap', min: null, max: null },
  { label: 'Under $2B', min: null, max: 2e9 },
  { label: '$2B – $10B', min: 2e9, max: 10e9 },
  { label: '$10B – $50B', min: 10e9, max: 50e9 },
  { label: '$50B – $200B', min: 50e9, max: 200e9 },
  { label: 'Above $200B', min: 200e9, max: null },
]

// Strategy parameters exposed in the form (label + step); everything else in
// parameters_json passes through untouched.
const PARAM_FIELDS = [
  { key: 'sma_short_window', label: 'SMA short', step: 1 },
  { key: 'sma_medium_window', label: 'SMA medium', step: 1 },
  { key: 'sma_long_window', label: 'SMA long', step: 1 },
  { key: 'sma_150_slope_lookback_days', label: 'Slope lookback (days)', step: 1 },
  { key: 'sma_150_min_slope_percent', label: 'Min slope %', step: 0.1 },
  { key: 'volume_average_days', label: 'Volume average days', step: 1 },
  { key: 'volume_multiplier', label: 'Volume multiplier', step: 0.1 },
]

function isoDaysAgo(days) {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

const inputCls =
  'w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none'
const labelCls = 'block text-xs text-slate-400'

function Field({ label, children }) {
  return (
    <label className="space-y-1">
      <span className={labelCls}>{label}</span>
      {children}
    </label>
  )
}

export default function BacktestNew() {
  const navigate = useNavigate()
  const strategies = useQuery({ queryKey: ['strategies'], queryFn: listStrategies })
  const scannerMeta = useQuery({
    queryKey: ['scanner-meta'],
    queryFn: () => getScanner({ limit: 1 }),
    staleTime: 300_000,
  })

  const [form, setForm] = useState({
    name: '',
    strategy_id: null,
    start_date: isoDaysAgo(365 * 5),
    end_date: isoDaysAgo(1),
    initial_cash: 100000,
    max_open_positions: 10,
    position_size_percent: 10,
    allow_fractional_shares: false,
    commission_per_trade: 0,
    slippage_percent: 0.05,
    benchmark_symbol: '^GSPC',
    symbols: '',
    sectors: [],
    capPreset: 0,
  })
  const [params, setParams] = useState({})
  const [submitError, setSubmitError] = useState(null)

  const strategy = useMemo(
    () =>
      strategies.data?.find((s) => s.id === form.strategy_id) ?? strategies.data?.[0] ?? null,
    [strategies.data, form.strategy_id],
  )

  // Seed editable parameters from the selected strategy's stored defaults.
  useEffect(() => {
    if (strategy) setParams({ ...strategy.parameters_json })
  }, [strategy])

  const create = useMutation({
    mutationFn: createBacktest,
    onSuccess: (run) => navigate(`/backtests/${run.id}`),
    onError: (err) =>
      setSubmitError(err.response?.data?.detail ?? err.message ?? 'Request failed'),
  })

  const set = (key) => (event) => {
    const { type, checked, value } = event.target
    setForm((f) => ({ ...f, [key]: type === 'checkbox' ? checked : value }))
  }

  function submit(event) {
    event.preventDefault()
    setSubmitError(null)
    const preset = CAP_PRESETS[form.capPreset]
    const symbols = form.symbols
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
    create.mutate({
      name:
        form.name.trim() ||
        `${strategy?.name ?? 'Backtest'} ${form.start_date} → ${form.end_date}`,
      strategy_id: strategy?.id ?? null,
      parameters: params,
      start_date: form.start_date,
      end_date: form.end_date,
      initial_cash: Number(form.initial_cash),
      symbols: symbols.length ? symbols : null,
      sectors: form.sectors.length ? form.sectors : null,
      min_market_cap: preset.min,
      max_market_cap: preset.max,
      max_open_positions: Number(form.max_open_positions),
      position_size_percent: Number(form.position_size_percent),
      allow_fractional_shares: form.allow_fractional_shares,
      commission_per_trade: Number(form.commission_per_trade),
      slippage_percent: Number(form.slippage_percent),
      benchmark_symbol: form.benchmark_symbol.trim() || null,
    })
  }

  const sectors = scannerMeta.data?.sectors ?? []

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">New backtest</h1>
        <Link to="/backtests" className="text-sm text-slate-400 hover:text-white">
          ← Back to backtests
        </Link>
      </div>

      <form onSubmit={submit} className="space-y-5">
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Setup</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <Field label="Name (optional)">
              <input
                className={inputCls}
                value={form.name}
                onChange={set('name')}
                placeholder="Auto-named from strategy + dates"
              />
            </Field>
            <Field label="Strategy">
              <select
                className={inputCls}
                value={strategy?.id ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, strategy_id: Number(e.target.value) }))}
              >
                {(strategies.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} v{s.version}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Start date">
              <input type="date" className={inputCls} value={form.start_date} onChange={set('start_date')} required />
            </Field>
            <Field label="End date">
              <input type="date" className={inputCls} value={form.end_date} onChange={set('end_date')} required />
            </Field>
            <Field label="Initial cash ($)">
              <input type="number" min="1000" step="1000" className={inputCls} value={form.initial_cash} onChange={set('initial_cash')} />
            </Field>
            <Field label="Benchmark symbol (empty = none)">
              <input className={inputCls} value={form.benchmark_symbol} onChange={set('benchmark_symbol')} placeholder="^GSPC" />
            </Field>
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
            Strategy parameters
          </h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            {PARAM_FIELDS.filter((f) => params[f.key] !== undefined).map(({ key, label, step }) => (
              <Field key={key} label={label}>
                <input
                  type="number"
                  step={step}
                  className={inputCls}
                  value={params[key]}
                  onChange={(e) =>
                    setParams((p) => ({ ...p, [key]: e.target.value === '' ? '' : Number(e.target.value) }))
                  }
                />
              </Field>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">Universe</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <Field label="Symbols (optional, comma-separated — empty = full S&P 500)">
              <input className={inputCls} value={form.symbols} onChange={set('symbols')} placeholder="AAPL, MSFT, NVDA" />
            </Field>
            <Field label="Market cap">
              <select
                className={inputCls}
                value={form.capPreset}
                onChange={(e) => setForm((f) => ({ ...f, capPreset: Number(e.target.value) }))}
              >
                {CAP_PRESETS.map((p, i) => (
                  <option key={p.label} value={i}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          {sectors.length > 0 && (
            <div className="mt-3">
              <span className={labelCls}>Sectors (none selected = all)</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {sectors.map((sector) => {
                  const active = form.sectors.includes(sector)
                  return (
                    <button
                      key={sector}
                      type="button"
                      onClick={() =>
                        setForm((f) => ({
                          ...f,
                          sectors: active
                            ? f.sectors.filter((s) => s !== sector)
                            : [...f.sectors, sector],
                        }))
                      }
                      className={`rounded-full border px-2.5 py-0.5 text-xs ${
                        active
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-300'
                          : 'border-slate-700 text-slate-400 hover:border-slate-500'
                      }`}
                    >
                      {sector}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
          <p className="mt-3 text-xs text-slate-500">
            Note: market-cap filters use <span className="text-slate-300">today's</span> caps
            (look-ahead when applied to past dates), and the universe is the current S&amp;P 500
            (survivorship bias).
          </p>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
            Portfolio &amp; costs
          </h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <Field label="Max open positions">
              <input type="number" min="1" max="200" className={inputCls} value={form.max_open_positions} onChange={set('max_open_positions')} />
            </Field>
            <Field label="Position size (% of equity)">
              <input type="number" min="0.1" max="100" step="0.1" className={inputCls} value={form.position_size_percent} onChange={set('position_size_percent')} />
            </Field>
            <label className="flex items-end gap-2 pb-1.5">
              <input type="checkbox" checked={form.allow_fractional_shares} onChange={set('allow_fractional_shares')} className="accent-emerald-500" />
              <span className="text-sm text-slate-300">Fractional shares</span>
            </label>
            <Field label="Commission per trade ($)">
              <input type="number" min="0" step="0.5" className={inputCls} value={form.commission_per_trade} onChange={set('commission_per_trade')} />
            </Field>
            <Field label="Slippage (%)">
              <input type="number" min="0" max="10" step="0.01" className={inputCls} value={form.slippage_percent} onChange={set('slippage_percent')} />
            </Field>
            <Field label="Execution">
              <input className={`${inputCls} text-slate-500`} value="Next market open" disabled />
            </Field>
          </div>
        </section>

        {submitError && (
          <p className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
            {typeof submitError === 'string' ? submitError : JSON.stringify(submitError)}
          </p>
        )}

        <button
          type="submit"
          disabled={create.isPending || !strategy}
          className="rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
        >
          {create.isPending ? 'Launching…' : 'Run backtest'}
        </button>
      </form>
    </div>
  )
}

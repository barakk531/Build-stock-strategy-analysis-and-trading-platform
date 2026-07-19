import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getConfig } from '../api/admin.js'
import { getApiKey, setApiKey } from '../api/client.js'
import { useHealth } from '../hooks/useHealth.js'

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800/60 py-2 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-200">{value ?? '—'}</span>
    </div>
  )
}

export default function Settings() {
  const queryClient = useQueryClient()
  const health = useHealth()
  const config = useQuery({ queryKey: ['admin-config'], queryFn: getConfig, retry: false })
  const [key, setKey] = useState(getApiKey())
  const [saved, setSaved] = useState(false)

  const authRequired = health.data?.auth_required
  const cfg = config.data

  function save(event) {
    event.preventDefault()
    setApiKey(key.trim())
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
    queryClient.invalidateQueries()
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
          API access
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          {authRequired
            ? 'This server requires an API key (ADMIN_API_KEY) for admin and trading endpoints.'
            : 'Authentication is currently disabled on the server (no ADMIN_API_KEY set) — fine for local use, required before public deployment.'}
        </p>
        <form onSubmit={save} className="mt-3 flex gap-2">
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="X-API-Key value"
            className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
          />
          <button
            type="submit"
            className="rounded bg-emerald-500 px-3 py-1.5 text-sm font-medium text-slate-950 hover:bg-emerald-400"
          >
            {saved ? 'Saved ✓' : 'Save'}
          </button>
        </form>
        <p className="mt-2 text-xs text-slate-600">
          Stored only in this browser (localStorage) and sent as the X-API-Key header.
        </p>
      </section>

      <section className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-sm font-medium tracking-wide text-slate-400 uppercase">
          Server configuration (read-only)
        </h2>
        {config.isError && (
          <p className="mt-2 text-sm text-amber-400">
            {config.error?.response?.status === 401
              ? 'Enter a valid API key above to view configuration.'
              : `Unavailable: ${config.error?.message}`}
          </p>
        )}
        {cfg && (
          <div className="mt-2">
            <Row label="Environment" value={`${cfg.environment} (v${cfg.version})`} />
            <Row label="Market timezone" value={cfg.market_timezone} />
            <Row label="Scheduler" value={cfg.scheduler_enabled ? 'enabled' : 'disabled'} />
            <Row label="Authentication" value={cfg.auth_required ? 'API key required' : 'disabled (dev)'} />
            <Row label="Price history" value={`${cfg.price_history_years} years, ${cfg.price_sync_overlap_days}-day resync overlap`} />
            <Row label="Telegram alerts" value={cfg.telegram.enabled ? `enabled (${cfg.telegram.alert_types})` : 'disabled'} />
            <Row label="Telegram bot token" value={cfg.telegram.bot_token ?? 'not set'} />
            <Row label="Telegram chat" value={cfg.telegram.chat_id ?? 'not set'} />
            <Row label="Chart links base" value={cfg.frontend_base_url} />
          </div>
        )}
        <p className="mt-3 text-xs text-slate-600">
          Values come from environment variables / .env — change them there and restart the
          backend. Secrets are always masked. See docs/deployment.md.
        </p>
      </section>
    </div>
  )
}

import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/scanner', label: 'Scanner' },
  { to: '/signals', label: 'Signals' },
  { to: '/strategies', label: 'Strategies' },
  { to: '/backtests', label: 'Backtests' },
  { to: '/paper-accounts', label: 'Paper Accounts' },
  { to: '/competitions', label: 'Competitions' },
  { to: '/settings', label: 'Settings' },
  { to: '/admin/data', label: 'Admin' },
]

// The Market Analyst is a separate Streamlit app on its own port; link out to
// it rather than routing internally. Override the URL with VITE_ANALYST_URL.
const ANALYST_URL = import.meta.env.VITE_ANALYST_URL || 'http://localhost:8501'

export default function Navbar() {
  return (
    <header className="border-b border-slate-800 bg-slate-900">
      <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <span className="text-lg font-semibold tracking-tight text-emerald-400">
          Stock Strategy Platform
        </span>
        <nav className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {links.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                isActive ? 'font-medium text-emerald-400' : 'text-slate-300 hover:text-white'
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <a
          href={ANALYST_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto rounded border border-emerald-500/40 px-2.5 py-1 text-sm font-medium text-emerald-400 hover:bg-emerald-500/10"
          title="Open the Market Analyst dashboard (separate app)"
        >
          📈 Market Analyst ↗
        </a>
      </div>
    </header>
  )
}

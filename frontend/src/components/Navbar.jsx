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
      </div>
    </header>
  )
}

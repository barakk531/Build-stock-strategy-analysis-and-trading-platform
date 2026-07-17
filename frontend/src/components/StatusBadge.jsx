const styles = {
  ok: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/30',
  degraded: 'bg-amber-500/15 text-amber-400 ring-amber-500/30',
  down: 'bg-red-500/15 text-red-400 ring-red-500/30',
  loading: 'bg-slate-500/15 text-slate-400 ring-slate-500/30',
}

export default function StatusBadge({ kind, children }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${styles[kind] ?? styles.loading}`}
    >
      {children}
    </span>
  )
}

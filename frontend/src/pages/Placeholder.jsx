export default function Placeholder({ title, phase }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 bg-slate-900/50 p-10 text-center">
      <h1 className="text-xl font-semibold text-slate-200">{title}</h1>
      <p className="mt-2 text-sm text-slate-400">
        This page arrives in Phase {phase} of the implementation plan.
      </p>
    </div>
  )
}

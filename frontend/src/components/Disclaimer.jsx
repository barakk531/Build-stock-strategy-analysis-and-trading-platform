export default function Disclaimer() {
  return (
    <footer className="border-t border-slate-800 bg-slate-900 px-4 py-4 text-xs text-slate-400">
      <div className="mx-auto max-w-7xl space-y-1">
        <p>
          This platform is for research, education, technical analysis, and simulated paper
          trading only. It does not provide personalized financial advice and does not guarantee
          investment results. Market data may be delayed, incomplete, or incorrect. Past or
          simulated performance does not guarantee future results.
        </p>
        <p>
          Market data: Yahoo Finance. All trading accounts on this platform are simulated (paper
          trading) — no real orders are ever placed.
        </p>
      </div>
    </footer>
  )
}

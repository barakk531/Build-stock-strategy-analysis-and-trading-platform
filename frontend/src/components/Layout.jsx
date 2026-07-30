import { Outlet } from 'react-router-dom'
import Disclaimer from './Disclaimer.jsx'
import MarketTicker from './market-ticker/MarketTicker.jsx'
import Navbar from './Navbar.jsx'

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      {/* Nav + ticker pinned together; sticky keeps them in flow so page
          content is never covered. */}
      <div className="sticky top-0 z-40">
        <Navbar />
        <MarketTicker />
      </div>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <Disclaimer />
    </div>
  )
}

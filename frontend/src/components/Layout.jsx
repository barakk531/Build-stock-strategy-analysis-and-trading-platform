import { Outlet } from 'react-router-dom'
import Disclaimer from './Disclaimer.jsx'
import Navbar from './Navbar.jsx'

export default function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <Disclaimer />
    </div>
  )
}

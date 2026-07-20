import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import BacktestDetail from './pages/BacktestDetail.jsx'
import BacktestNew from './pages/BacktestNew.jsx'
import Backtests from './pages/Backtests.jsx'
import AdminData from './pages/AdminData.jsx'
import CompetitionDetail from './pages/CompetitionDetail.jsx'
import Competitions from './pages/Competitions.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Settings from './pages/Settings.jsx'
import PaperAccountDetail from './pages/PaperAccountDetail.jsx'
import PaperAccountNew from './pages/PaperAccountNew.jsx'
import PaperAccounts from './pages/PaperAccounts.jsx'
import Scanner from './pages/Scanner.jsx'
import Signals from './pages/Signals.jsx'
import StockDetail from './pages/StockDetail.jsx'
import Strategies from './pages/Strategies.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scanner" element={<Scanner />} />
        <Route path="/stocks/:symbol" element={<StockDetail />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/strategies" element={<Strategies />} />
        <Route path="/backtests" element={<Backtests />} />
        <Route path="/backtests/new" element={<BacktestNew />} />
        <Route path="/backtests/:id" element={<BacktestDetail />} />
        <Route path="/paper-accounts" element={<PaperAccounts />} />
        <Route path="/paper-accounts/new" element={<PaperAccountNew />} />
        <Route path="/paper-accounts/:id" element={<PaperAccountDetail />} />
        <Route path="/competitions" element={<Competitions />} />
        <Route path="/competitions/:id" element={<CompetitionDetail />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/admin/data" element={<AdminData />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

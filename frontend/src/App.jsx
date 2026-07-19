import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import BacktestDetail from './pages/BacktestDetail.jsx'
import BacktestNew from './pages/BacktestNew.jsx'
import Backtests from './pages/Backtests.jsx'
import Dashboard from './pages/Dashboard.jsx'
import PaperAccountDetail from './pages/PaperAccountDetail.jsx'
import PaperAccountNew from './pages/PaperAccountNew.jsx'
import PaperAccounts from './pages/PaperAccounts.jsx'
import Placeholder from './pages/Placeholder.jsx'
import Scanner from './pages/Scanner.jsx'
import StockDetail from './pages/StockDetail.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scanner" element={<Scanner />} />
        <Route path="/stocks/:symbol" element={<StockDetail />} />
        <Route path="/signals" element={<Placeholder title="Signals" phase={3} />} />
        <Route path="/strategies" element={<Placeholder title="Strategies" phase={3} />} />
        <Route path="/backtests" element={<Backtests />} />
        <Route path="/backtests/new" element={<BacktestNew />} />
        <Route path="/backtests/:id" element={<BacktestDetail />} />
        <Route path="/paper-accounts" element={<PaperAccounts />} />
        <Route path="/paper-accounts/new" element={<PaperAccountNew />} />
        <Route path="/paper-accounts/:id" element={<PaperAccountDetail />} />
        <Route
          path="/competitions"
          element={<Placeholder title="Strategy Competition" phase={8} />}
        />
        <Route path="/settings" element={<Placeholder title="Settings" phase={9} />} />
        <Route path="/admin/data" element={<Placeholder title="Data Administration" phase={2} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Placeholder from './pages/Placeholder.jsx'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scanner" element={<Placeholder title="Stock Scanner" phase={4} />} />
        <Route path="/stocks/:symbol" element={<Placeholder title="Stock Detail" phase={4} />} />
        <Route path="/signals" element={<Placeholder title="Signals" phase={3} />} />
        <Route path="/strategies" element={<Placeholder title="Strategies" phase={3} />} />
        <Route path="/backtests" element={<Placeholder title="Backtests" phase={6} />} />
        <Route path="/paper-accounts" element={<Placeholder title="Paper Accounts" phase={7} />} />
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

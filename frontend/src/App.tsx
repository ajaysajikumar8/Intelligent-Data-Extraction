import { Navigate, Route, Routes } from 'react-router-dom'
import { DashboardLayout } from './components/layout/DashboardLayout'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { Login } from './pages/Login'
import { Signup } from './pages/Signup'
import { Dashboard } from './pages/Dashboard'
import { Submit } from './pages/Submit'
import { Logs } from './pages/Logs'
import { Templates } from './pages/Templates'
import { Settings } from './pages/Settings'
import { Integrations } from './pages/Integrations'
import { NotFound } from './pages/NotFound'

export function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login"  element={<Login />} />
      <Route path="/signup" element={<Signup />} />

      {/* Protected routes — require auth token */}
      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"  element={<Dashboard />} />
          <Route path="/submit"     element={<Submit />} />
          <Route path="/logs"       element={<Logs />} />
          <Route path="/templates"  element={<Templates />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/settings"   element={<Settings />} />
        </Route>
      </Route>

      {/* Catch-all */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

import { Navigate, Outlet } from 'react-router-dom'
import { isAuthenticated } from '../../lib/auth'

/**
 * ProtectedRoute — wraps all authenticated routes.
 * Redirects to /login if no token is found in localStorage.
 * Renders the nested <Outlet> (the dashboard layout + page) otherwise.
 */
export function ProtectedRoute() {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

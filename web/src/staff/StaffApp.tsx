import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { AuthProvider, LoginPage, useAuth } from './auth'
import type { Role } from './auth'
import Appeals from './pages/Appeals'
import AuditLog from './pages/AuditLog'
import ConfigEditor from './pages/ConfigEditor'
import Confirmations from './pages/Confirmations'
import ContactRequests from './pages/ContactRequests'
import ContentJobs from './pages/ContentJobs'
import Dashboard from './pages/Dashboard'
import Mirror from './pages/Mirror'
import Monitoring from './pages/Monitoring'
import Outliers from './pages/Outliers'
import ResidentDetail from './pages/ResidentDetail'
import Roster from './pages/Roster'
import ViewAs from './pages/ViewAs'
import Welfare from './pages/Welfare'

const SUPERVISION: Role[] = ['supervisor', 'admin', 'auditor']
const NAV: { to: string; label: string; roles?: Role[] }[] = [
  { to: '/staff', label: 'Dashboard' },
  { to: '/staff/roster', label: 'Roster' },
  { to: '/staff/welfare', label: 'Welfare' },
  { to: '/staff/contacts', label: 'Contacts', roles: ['officer', 'supervisor', 'admin'] },
  { to: '/staff/monitoring', label: 'Monitoring', roles: SUPERVISION },
  { to: '/staff/confirmations', label: 'Confirmations', roles: SUPERVISION },
  { to: '/staff/appeals', label: 'Appeals', roles: SUPERVISION },
  { to: '/staff/outliers', label: 'Outliers', roles: SUPERVISION },
  { to: '/staff/view-as', label: 'View as' },
  { to: '/staff/mirror', label: 'Live mirror', roles: SUPERVISION },
  { to: '/staff/content', label: 'Content & jobs' },
  { to: '/staff/config', label: 'Config' },
  { to: '/staff/audit', label: 'Audit log', roles: ['admin', 'auditor'] },
]

function Guard({ roles, children }: { roles?: Role[]; children: React.ReactNode }) {
  const { user } = useAuth()
  if (roles && user && !roles.includes(user.role))
    return <p role="alert">Your role cannot open this page.</p>
  return <>{children}</>
}

function Shell() {
  const { user, loading, logout } = useAuth()
  if (loading) return <p className="p-6">Loading…</p>
  if (!user) return <LoginPage />
  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <strong>ISD Staff</strong>
          <nav className="flex flex-wrap gap-1" aria-label="Main">
            {NAV.filter((n) => !n.roles || n.roles.includes(user.role)).map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/staff'}
                className={({ isActive }) =>
                  `rounded px-3 py-1.5 text-sm ${isActive ? 'bg-blue-700 text-white' : 'hover:bg-gray-100'}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <span className="ml-auto text-sm" data-testid="whoami">
            {user.username} ({user.role})
          </span>
          <button onClick={logout} className="rounded border px-3 py-1.5 text-sm">
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-4 p-4">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="roster" element={<Roster />} />
          <Route path="residents/:id" element={<ResidentDetail />} />
          <Route
            path="confirmations"
            element={
              <Guard roles={SUPERVISION}>
                <Confirmations />
              </Guard>
            }
          />
          <Route
            path="appeals"
            element={
              <Guard roles={SUPERVISION}>
                <Appeals />
              </Guard>
            }
          />
          <Route
            path="outliers"
            element={
              <Guard roles={SUPERVISION}>
                <Outliers />
              </Guard>
            }
          />
          <Route path="view-as" element={<ViewAs />} />
          <Route
            path="mirror"
            element={
              <Guard roles={SUPERVISION}>
                <Mirror />
              </Guard>
            }
          />
          <Route path="welfare" element={<Welfare />} />
          <Route
            path="contacts"
            element={
              <Guard roles={['officer', 'supervisor', 'admin']}>
                <ContactRequests />
              </Guard>
            }
          />
          <Route
            path="monitoring"
            element={
              <Guard roles={SUPERVISION}>
                <Monitoring />
              </Guard>
            }
          />
          <Route path="content" element={<ContentJobs />} />
          <Route path="config" element={<ConfigEditor />} />
          <Route
            path="audit"
            element={
              <Guard roles={['admin', 'auditor']}>
                <AuditLog />
              </Guard>
            }
          />
          <Route path="*" element={<Navigate to="/staff" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function StaffApp() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  )
}

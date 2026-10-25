import {
  BarChart3,
  BookOpen,
  CalendarDays,
  CheckCheck,
  ClipboardList,
  Contact,
  DoorOpen,
  Eye,
  HeartPulse,
  Landmark,
  Languages,
  LayoutDashboard,
  LineChart,
  LogOut,
  MonitorPlay,
  Palette,
  Radio,
  Scale,
  ScrollText,
  Settings,
  ShieldCheck,
  Tablet,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { api } from './api'

import { AuthProvider, LoginPage, useAuth } from './auth'
import type { Role } from './auth'
import Appeals from './pages/Appeals'
import AuditLog from './pages/AuditLog'
import ConfigEditor from './pages/ConfigEditor'
import Confirmations from './pages/Confirmations'
import ContactRequests from './pages/ContactRequests'
import ContentJobs from './pages/ContentJobs'
import Dashboard from './pages/Dashboard'
import Finance from './pages/Finance'
import Mirror from './pages/Mirror'
import Monitoring from './pages/Monitoring'
import OutOfCell from './pages/OutOfCell'
import Outliers from './pages/Outliers'
import ResidentDetail from './pages/ResidentDetail'
import Schedule from './pages/Schedule'
import Roster from './pages/Roster'
import ViewAs from './pages/ViewAs'
import Certificates from './pages/Certificates'
import Devices from './pages/Devices'
import Intake from './pages/Intake'
import Outcomes from './pages/Outcomes'
import Welfare from './pages/Welfare'
import Styleguide from './pages/Styleguide'

const SUPERVISION: Role[] = ['supervisor', 'admin', 'auditor']
interface NavItem {
  to: string
  key: string
  icon: LucideIcon
  roles?: Role[]
  /** Which summary count to show as a badge. */
  badge?: 'pending_confirmations' | 'open_appeals' | 'welfare_flags' | 'offline_devices'
}
const NAV_GROUPS: { key: string; items: NavItem[] }[] = [
  {
    key: 'today',
    items: [
      { to: '/staff', key: 'dashboard', icon: LayoutDashboard },
      { to: '/staff/roster', key: 'roster', icon: Users },
      { to: '/staff/welfare', key: 'welfare', icon: HeartPulse, badge: 'welfare_flags' },
      { to: '/staff/out-of-cell', key: 'outOfCell', icon: DoorOpen },
      { to: '/staff/schedule', key: 'schedule', icon: CalendarDays },
      { to: '/staff/devices', key: 'devices', icon: Tablet, badge: 'offline_devices' },
    ],
  },
  {
    key: 'decisions',
    items: [
      {
        to: '/staff/confirmations',
        key: 'confirmations',
        icon: CheckCheck,
        roles: SUPERVISION,
        badge: 'pending_confirmations',
      },
      {
        to: '/staff/appeals',
        key: 'appeals',
        icon: Scale,
        roles: SUPERVISION,
        badge: 'open_appeals',
      },
      { to: '/staff/outliers', key: 'outliers', icon: BarChart3, roles: SUPERVISION },
      {
        to: '/staff/contacts',
        key: 'contacts',
        icon: Contact,
        roles: ['officer', 'supervisor', 'admin'],
      },
      { to: '/staff/monitoring', key: 'monitoring', icon: Eye, roles: SUPERVISION },
    ],
  },
  {
    key: 'tools',
    items: [
      { to: '/staff/view-as', key: 'viewAs', icon: MonitorPlay },
      { to: '/staff/mirror', key: 'mirror', icon: Radio, roles: SUPERVISION },
      { to: '/staff/intake', key: 'intake', icon: ClipboardList, roles: ['supervisor', 'admin'] },
      { to: '/staff/content', key: 'content', icon: BookOpen },
    ],
  },
  {
    key: 'admin',
    items: [
      { to: '/staff/finance', key: 'finance', icon: Landmark, roles: SUPERVISION },
      { to: '/staff/outcomes', key: 'outcomes', icon: LineChart, roles: SUPERVISION },
      { to: '/staff/config', key: 'config', icon: Settings },
      { to: '/staff/audit', key: 'audit', icon: ScrollText, roles: ['admin', 'auditor'] },
      { to: '/staff/styleguide', key: 'styleguide', icon: Palette },
    ],
  },
]

type Counts = Partial<Record<NonNullable<NavItem['badge']>, number>>

/** Pending counts for the nav badges: always visible, refreshed every 30 seconds. */
function useCounts(enabled: boolean): Counts {
  const [counts, setCounts] = useState<Counts>({})
  useEffect(() => {
    if (!enabled) return
    let live = true
    const load = () =>
      api<Counts>('/staff/summary')
        .then((c) => live && setCounts(c))
        .catch(() => {})
    void load()
    const id = setInterval(load, 30_000)
    return () => {
      live = false
      clearInterval(id)
    }
  }, [enabled])
  return counts
}

function Guard({ roles, children }: { roles?: Role[]; children: React.ReactNode }) {
  const { user } = useAuth()
  const { t } = useTranslation()
  if (roles && user && !roles.includes(user.role))
    return <p role="alert">{t('staff.roleDenied')}</p>
  return <>{children}</>
}

function Shell() {
  const { t, i18n } = useTranslation()
  const { user, loading, logout } = useAuth()
  const counts = useCounts(Boolean(user))
  if (loading) return null
  if (!user) return <LoginPage />
  const other = i18n.language === 'es' ? 'en' : 'es'
  return (
    <div className="theme-staff min-h-screen bg-bg text-body text-ink lg:grid lg:grid-cols-[15rem_1fr]">
      <a
        href="#staff-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-ctl focus:bg-surface focus:p-3"
      >
        {t('staff.skip')}
      </a>
      <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-2 px-4 py-3 text-h3 font-bold">
          <ShieldCheck aria-hidden="true" className="size-6 text-primary" />
          {t('staff.brand')}
        </div>
        <nav aria-label={t('staff.mainNav')} className="space-y-3 px-2 pb-4">
          {NAV_GROUPS.map((g) => {
            const items = g.items.filter((n) => !n.roles || n.roles.includes(user.role))
            if (!items.length) return null
            return (
              <div key={g.key}>
                <p className="px-3 pb-1 text-sm font-bold text-ink-soft">
                  {t(`staff.nav.${g.key}`)}
                </p>
                <ul className="space-y-0.5">
                  {items.map((n) => {
                    const count = n.badge ? counts[n.badge] : undefined
                    return (
                      <li key={n.to}>
                        <NavLink
                          to={n.to}
                          end={n.to === '/staff'}
                          className={({ isActive }) =>
                            `flex min-h-8 items-center gap-2 rounded-ctl px-3 py-1 font-medium ${
                              isActive
                                ? 'bg-primary text-primary-ink'
                                : 'text-ink hover:bg-surface-2'
                            }`
                          }
                        >
                          <n.icon aria-hidden="true" className="size-[1.125rem] shrink-0" />
                          <span className="flex-1">{t(`staff.nav.${n.key}`)}</span>
                          {count ? (
                            <span
                              data-testid={`nav-count-${n.key}`}
                              className="rounded-full bg-notice-soft px-2 text-sm font-bold text-notice"
                              aria-label={t('staff.waiting', { count })}
                            >
                              {count}
                            </span>
                          ) : null}
                        </NavLink>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )
          })}
        </nav>
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-end gap-3 border-b border-line bg-surface px-6 py-2">
          <span className="mr-auto text-ink-soft" data-testid="whoami">
            {user.username} ({user.role})
          </span>
          <button
            onClick={() => void i18n.changeLanguage(other)}
            lang={other}
            className="inline-flex min-h-touch items-center gap-1.5 rounded-ctl border border-ink-soft px-3 font-medium hover:bg-surface-2"
          >
            <Languages aria-hidden="true" className="size-4" />
            {t('staff.otherLanguage')}
          </button>
          <button
            onClick={logout}
            className="inline-flex min-h-touch items-center gap-1.5 rounded-ctl border border-ink-soft px-3 font-medium hover:bg-surface-2"
          >
            <LogOut aria-hidden="true" className="size-4" />
            {t('staff.signOut')}
          </button>
        </header>
        <main id="staff-main" className="space-y-4 p-6">
          <Routes>
            <Route index element={<Dashboard />} />
            <Route path="roster" element={<Roster />} />
            <Route path="devices" element={<Devices />} />
            <Route
              path="intake"
              element={
                <Guard roles={['supervisor', 'admin']}>
                  <Intake />
                </Guard>
              }
            />
            <Route
              path="outcomes"
              element={
                <Guard roles={SUPERVISION}>
                  <Outcomes />
                </Guard>
              }
            />
            <Route path="residents/:id" element={<ResidentDetail />} />
            <Route path="residents/:id/certificates" element={<Certificates />} />
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
            <Route path="out-of-cell" element={<OutOfCell />} />
            <Route path="schedule" element={<Schedule />} />
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
            <Route
              path="finance"
              element={
                <Guard roles={SUPERVISION}>
                  <Finance />
                </Guard>
              }
            />
            <Route path="config" element={<ConfigEditor />} />
            <Route
              path="audit"
              element={
                <Guard roles={['admin', 'auditor']}>
                  <AuditLog />
                </Guard>
              }
            />
            <Route path="styleguide" element={<Styleguide />} />
            <Route path="*" element={<Navigate to="/staff" replace />} />
          </Routes>
        </main>
      </div>
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

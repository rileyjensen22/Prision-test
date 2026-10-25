import { useCallback, useEffect, useState } from 'react'
import { HandHelping, Tablet } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { RequestStaffDialog } from './RequestStaff'
import { ResidentProvider, useResident } from './ResidentContext'
import { Calls } from './features/Calls'
import { Commissary } from './features/Commissary'
import { Contacts } from './features/Contacts'
import { Jobs } from './features/Jobs'
import { Reading } from './features/Reading'
import { Rec } from './features/Rec'
import { Texting } from './features/Texting'
import { Video } from './features/Video'
import { Pairing } from './Pairing'
import { Reentry } from './features/Reentry'
import { CertificateView, Certificates, Course, Education } from './features/Education'
import { Appeal, FeaturePage, Home, Locks, TierScreen } from './screens'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { LoadingState } from '../ui/States'
import { DEFAULT_NIGHT, isNight, type NightWindow } from './nightMode'
import { TEXT_SIZE } from './theme'
import { useInactivity } from './useInactivity'

function Shell() {
  const { t } = useTranslation()
  const { status, view, online, stale, pending, request, now } = useResident()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState(false)
  const goHome = useCallback(() => {
    setDialog(false)
    navigate('/resident', { replace: true })
  }, [navigate])
  useInactivity(view?.ui.inactivity_return_home_seconds ?? 90, goHome)

  useEffect(() => {
    // Tell the server which screen this is, so a logged live mirror can follow along.
    // Best effort: failing (offline) must never affect the resident.
    if (status === 'ready')
      void request('/device/screen', {
        method: 'POST',
        body: JSON.stringify({ path: pathname }),
      }).catch(() => {})
  }, [pathname, status, request])

  useEffect(() => {
    // Kiosk: no context menu or drag-and-drop navigation.
    const block = (e: Event) => e.preventDefault()
    window.addEventListener('contextmenu', block)
    window.addEventListener('dragstart', block)
    return () => {
      window.removeEventListener('contextmenu', block)
      window.removeEventListener('dragstart', block)
    }
  }, [])

  const size = TEXT_SIZE[view?.settings.text_size ?? 'normal']
  const night = useNight(view?.ui.night_mode, now)
  const message =
    status === 'no-device'
      ? t('app.notSetUp')
      : status === 'unassigned'
        ? t('app.notAssigned')
        : status === 'loading' || !view
          ? t('app.loading')
          : null

  return (
    <div
      className={`theme-resident flex min-h-screen flex-col bg-bg text-body text-ink ${size}`}
      data-mode={night ? 'night' : 'day'}
      data-testid="kiosk"
    >
      {view?.simulation && <Banner tone="simulation">{t('app.simulation')}</Banner>}
      {(!online || stale) && view && (
        <Banner tone="offline" role="status" data-testid="connection-banner">
          {stale ? t('app.stale') : t('app.offline')}
        </Banner>
      )}
      <main className="flex-1 px-6 py-6 lg:px-10">
        {message ? (
          <div className="mx-auto max-w-2xl space-y-6 pt-12">
            {status === 'loading' ? (
              <LoadingState title={message} />
            ) : (
              <div className="flex flex-col items-center gap-4 rounded-card border border-line bg-surface px-8 py-12 text-center shadow-card">
                <Tablet aria-hidden="true" className="size-14 text-primary" strokeWidth={1.5} />
                <p data-testid="status-message" className="text-h3 font-bold">
                  {message}
                </p>
              </div>
            )}
            {status === 'no-device' && <Pairing />}
          </div>
        ) : (
          <Routes>
            <Route index element={<Home />} />
            <Route path="locks" element={<Locks />} />
            <Route path="appeal/:sanctionId" element={<Appeal />} />
            <Route path="tier" element={<TierScreen />} />
            <Route path="feature/calls" element={<Calls />} />
            <Route path="feature/commissary" element={<Commissary />} />
            <Route path="feature/basic_education" element={<Education />} />
            <Route path="feature/advanced_education" element={<Education />} />
            <Route path="feature/texting" element={<Texting />} />
            <Route path="feature/video" element={<Video />} />
            <Route path="feature/contact_requests" element={<Contacts />} />
            <Route path="feature/reading_general" element={<Reading />} />
            <Route path="feature/reading_expanded" element={<Reading />} />
            <Route path="feature/outdoor_rec" element={<Rec />} />
            <Route path="feature/out_of_cell_minimum" element={<Rec />} />
            <Route path="jobs" element={<Jobs />} />
            <Route path="course/:code" element={<Course />} />
            <Route path="reentry" element={<Reentry />} />
            <Route path="certificates" element={<Certificates />} />
            <Route path="certificate/:serial" element={<CertificateView />} />
            <Route path="feature/:name" element={<FeaturePage />} />
          </Routes>
        )}
      </main>
      <footer className="sticky bottom-0 z-10 border-t-2 border-line bg-surface px-6 py-3 lg:px-10">
        <div className="mx-auto flex max-w-[1500px] items-center gap-4">
          {pending > 0 && (
            <span data-testid="pending-count" className="text-sm text-ink-soft">
              {t('app.pending', { count: pending })}
            </span>
          )}
          <Button
            variant="secondary"
            icon={HandHelping}
            onClick={() => setDialog(true)}
            disabled={status === 'no-device'}
            className="ml-auto border-primary bg-primary text-primary-ink hover:bg-primary hover:brightness-110"
          >
            {t('request.button')}
          </Button>
        </div>
      </footer>
      {dialog && <RequestStaffDialog onClose={() => setDialog(false)} />}
    </div>
  )
}

/** Day or night: ?mode= wins (for screenshots and tests), then the schedule, then the default. */
function useNight(schedule: NightWindow | undefined, nowMs: number): boolean {
  // ?mode= forces a mode, for screenshots and tests. A real kiosk follows the schedule.
  const forced = new URLSearchParams(useLocation().search).get('mode')
  if (forced === 'night') return true
  if (forced === 'day') return false
  return isNight(new Date(nowMs), schedule ?? DEFAULT_NIGHT)
}

export default function ResidentApp() {
  return (
    <ResidentProvider>
      <Shell />
    </ResidentProvider>
  )
}

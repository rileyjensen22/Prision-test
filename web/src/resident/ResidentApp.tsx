import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Route, Routes, useNavigate } from 'react-router-dom'

import { RequestStaffDialog } from './RequestStaff'
import { ResidentProvider, useResident } from './ResidentContext'
import { Appeal, FeaturePage, Home, Locks, TierScreen } from './screens'
import { useInactivity } from './useInactivity'

const TEXT_SIZE = { normal: 'text-2xl', large: 'text-3xl', xlarge: 'text-4xl' } as const

function Shell() {
  const { t } = useTranslation()
  const { status, view, online, stale, pending } = useResident()
  const navigate = useNavigate()
  const [dialog, setDialog] = useState(false)
  const goHome = useCallback(() => {
    setDialog(false)
    navigate('/resident', { replace: true })
  }, [navigate])
  useInactivity(view?.ui.inactivity_return_home_seconds ?? 90, goHome)

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
  const message =
    status === 'no-device'
      ? t('app.notSetUp')
      : status === 'unassigned'
        ? t('app.notAssigned')
        : status === 'loading' || !view
          ? t('app.loading')
          : null

  return (
    <div className={`min-h-screen bg-slate-950 pb-32 text-white ${size}`} data-testid="kiosk">
      {view?.simulation && (
        <div className="bg-red-700 p-2 text-center font-bold">{t('app.simulation')}</div>
      )}
      {(!online || stale) && view && (
        <div role="status" data-testid="connection-banner" className="bg-amber-400 p-3 text-black">
          {stale ? t('app.stale') : t('app.offline')}
        </div>
      )}
      <main className="mx-auto max-w-3xl space-y-6 p-6">
        {message ? (
          <p data-testid="status-message">{message}</p>
        ) : (
          <Routes>
            <Route index element={<Home />} />
            <Route path="locks" element={<Locks />} />
            <Route path="appeal/:sanctionId" element={<Appeal />} />
            <Route path="tier" element={<TierScreen />} />
            <Route path="feature/:name" element={<FeaturePage />} />
          </Routes>
        )}
      </main>
      <footer className="fixed inset-x-0 bottom-0 z-10 border-t-2 border-white bg-slate-900 p-4">
        <div className="mx-auto flex max-w-3xl items-center gap-4">
          <button
            onClick={() => setDialog(true)}
            disabled={status === 'no-device'}
            className="min-h-16 flex-1 rounded-xl bg-blue-700 px-6 py-4 text-xl font-bold"
          >
            {t('request.button')}
          </button>
          {pending > 0 && (
            <span data-testid="pending-count">{t('app.pending', { count: pending })}</span>
          )}
        </div>
      </footer>
      {dialog && <RequestStaffDialog onClose={() => setDialog(false)} />}
    </div>
  )
}

export default function ResidentApp() {
  return (
    <ResidentProvider>
      <Shell />
    </ResidentProvider>
  )
}

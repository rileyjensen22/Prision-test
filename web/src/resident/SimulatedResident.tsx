import { useLayoutEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { I18nextProvider, useTranslation } from 'react-i18next'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'

import { createI18n } from '../i18n'
import { Card } from './components'
import { StaticResidentProvider, useResident } from './ResidentContext'
import { Appeal, Home, Locks, TierScreen } from './screens'
import { TEXT_SIZE } from './theme'
import type { ResidentView } from './types'

/** Stand-in for screens whose content is live data (calls, shop, classes) in sandbox and mirror. */
function LiveScreen({ name }: { name: string }) {
  const { t } = useTranslation()
  const { features } = useResident()
  const f = features[name]
  return (
    <div className="space-y-4" data-testid="sim-live-screen">
      <h1 className="text-3xl font-bold">
        {name ? t(`feature.${name}`, { defaultValue: name }) : ''}
      </h1>
      <Card>
        <p>{f?.allowed === false ? `🔒 ${t('home.locked')}` : t('home.open')}</p>
        {f &&
          Object.entries(f.limits).map(([k, v]) => (
            <p key={k}>
              {k}: {v}
            </p>
          ))}
        <p className="mt-2 text-base opacity-80">Live content is not shown in this view.</p>
      </Card>
    </div>
  )
}

function Screens() {
  return (
    <Routes>
      <Route path="/resident" element={<Home />} />
      <Route path="/resident/locks" element={<Locks />} />
      <Route path="/resident/appeal/:sanctionId" element={<Appeal />} />
      <Route path="/resident/tier" element={<TierScreen />} />
      <Route path="/resident/feature/:name" element={<FeatureRoute />} />
      <Route path="*" element={<LiveScreen name="" />} />
    </Routes>
  )
}

function FeatureRoute() {
  const { name = '' } = useParams()
  return <LiveScreen name={name} />
}

/**
 * Renders children in their own React root. The simulated resident app needs its own router, and
 * React Router refuses to nest one router inside another (the staff app already has one).
 */
function Isolated({ children }: { children: ReactNode }) {
  const host = useRef<HTMLDivElement>(null)
  const root = useRef<Root | null>(null)
  useLayoutEffect(() => {
    root.current = createRoot(host.current as HTMLDivElement)
    return () => {
      const r = root.current
      root.current = null
      setTimeout(() => r?.unmount()) // never unmount a root while its parent is committing
    }
  }, [])
  useLayoutEffect(() => {
    root.current?.render(children)
  })
  return <div ref={host} />
}

/**
 * The real resident screens, rendered from a ResidentView with no device, network or writes.
 * `sandbox`: staff can click around. `mirror`: read-only, follows `path`.
 */
export function SimulatedResident({
  view,
  mode,
  path = '/resident',
}: {
  view: ResidentView
  mode: 'sandbox' | 'mirror'
  path?: string
}) {
  const i18n = useMemo(() => createI18n(view.settings.language), [view.settings.language])
  return (
    <Isolated>
      <I18nextProvider i18n={i18n}>
        <StaticResidentProvider view={view}>
          <MemoryRouter key={mode === 'mirror' ? path : 'sandbox'} initialEntries={[path]}>
            <div
              className={`rounded-lg bg-slate-950 text-white ${TEXT_SIZE[view.settings.text_size]}`}
              data-testid="sim-screen"
              data-mode={mode}
            >
              {view.simulation && (
                <div className="rounded-t-lg bg-red-700 p-2 text-center font-bold">
                  {i18n.t('app.simulation')}
                </div>
              )}
              <div
                className={`space-y-6 p-6 ${mode === 'mirror' ? 'pointer-events-none select-none' : ''}`}
                aria-readonly={mode === 'mirror'}
                data-testid="sim-body"
              >
                <Screens />
                <div className="rounded-xl bg-blue-700 px-6 py-4 text-center font-bold">
                  {i18n.t('request.button')}
                </div>
              </div>
            </div>
          </MemoryRouter>
        </StaticResidentProvider>
      </I18nextProvider>
    </Isolated>
  )
}

import React, { useMemo, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import '../i18n'
import '../index.css'
import ResidentApp from '../resident/ResidentApp'
import { installShim, SCENARIOS, type DemoState, type Scenario } from './shim'

// Storage can be blocked in a sandboxed page, so the demo keeps its own in-memory copy.
function memoryStorage(): Storage {
  const m = new Map<string, string>()
  return {
    get length() {
      return m.size
    },
    clear: () => m.clear(),
    getItem: (k) => m.get(k) ?? null,
    key: (i) => [...m.keys()][i] ?? null,
    removeItem: (k) => void m.delete(k),
    setItem: (k, v) => void m.set(k, String(v)),
  }
}
for (const name of ['localStorage', 'sessionStorage'] as const)
  Object.defineProperty(window, name, { value: memoryStorage(), configurable: true })
window.localStorage.setItem('isd.deviceToken', 'demo-token')

function Demo() {
  const [scenario, setScenario] = useState<Scenario>('alice')
  const [language, setLanguage] = useState<'en' | 'es'>('en')
  const [run, setRun] = useState(0)
  // Installed during render so it is in place before the kiosk's first fetch after a switch.
  const state = useMemo<DemoState>(() => {
    window.localStorage.clear()
    window.localStorage.setItem('isd.deviceToken', 'demo-token')
    const next: DemoState = { scenario, language, passed: false, balance: 2000 }
    installShim(next)
    return next
  }, [scenario, language, run])
  void state
  const info = SCENARIOS.find((s) => s.id === scenario)!

  return (
    <div style={{ background: '#0f172a', minHeight: '100vh' }}>
      <div
        style={{
          padding:
            '10px max(16px, env(safe-area-inset-right)) 10px max(16px, env(safe-area-inset-left))',
          color: '#e2e8f0',
          font: '14px system-ui, sans-serif',
        }}
      >
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              onClick={() => setScenario(s.id)}
              style={{
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid #475569',
                background: s.id === scenario ? '#2563eb' : 'transparent',
                color: '#fff',
              }}
            >
              {s.title}
            </button>
          ))}
          <button
            onClick={() => setLanguage(language === 'en' ? 'es' : 'en')}
            style={{
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid #475569',
              background: 'transparent',
              color: '#fff',
            }}
          >
            {language === 'en' ? 'Español' : 'English'}
          </button>
          <button
            onClick={() => setRun(run + 1)}
            style={{
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid #475569',
              background: 'transparent',
              color: '#fff',
            }}
          >
            Reset
          </button>
        </div>
        <p style={{ margin: '8px 0 0', opacity: 0.8 }}>
          {info.blurb} Sample data only; nothing is saved.
        </p>
      </div>
      {
        <MemoryRouter key={`${scenario}-${language}-${run}`} initialEntries={['/resident']}>
          <Routes>
            <Route path="/resident/*" element={<ResidentApp />} />
          </Routes>
        </MemoryRouter>
      }
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Demo />
  </React.StrictMode>,
)

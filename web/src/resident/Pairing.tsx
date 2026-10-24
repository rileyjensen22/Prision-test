import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TOKEN_KEY } from './api'

/** First boot: the kiosk trades the one-time code staff give it for its own device token. */
export function Pairing() {
  const { t } = useTranslation()
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function pair(value: string) {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/device/pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: value.trim() }),
      })
      if (!res.ok) throw new Error(String(res.status))
      const { token } = (await res.json()) as { token: string }
      localStorage.setItem(TOKEN_KEY, token)
      window.location.replace('/resident')
    } catch {
      setError(t('pairing.failed'))
      setBusy(false)
    }
  }

  useEffect(() => {
    // `/resident#pair=CODE` lets a provisioning script start the pairing without typing.
    const fromHash = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('pair')
    if (fromHash) {
      window.history.replaceState(null, '', window.location.pathname)
      void pair(fromHash)
    }
  }, [])

  return (
    <form
      className="space-y-4"
      data-testid="pairing"
      onSubmit={(e) => {
        e.preventDefault()
        void pair(code)
      }}
    >
      <h1 className="text-3xl font-bold">{t('pairing.title')}</h1>
      <p>{t('pairing.help')}</p>
      <label className="block text-xl">
        {t('pairing.code')}
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          autoComplete="off"
          autoCapitalize="characters"
          maxLength={16}
          className="mt-2 block min-h-14 w-full rounded-lg border-2 border-white bg-slate-900 px-4 font-mono text-2xl"
        />
      </label>
      {error && <p role="alert">{error}</p>}
      <button
        type="submit"
        disabled={busy || code.trim().length < 6}
        className="min-h-14 rounded-lg bg-blue-700 px-6 py-3 font-semibold disabled:opacity-40"
      >
        {t('pairing.connect')}
      </button>
    </form>
  )
}

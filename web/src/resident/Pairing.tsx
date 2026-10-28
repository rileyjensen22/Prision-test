import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Link2 } from 'lucide-react'

import { Button } from '../ui/Button'
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
      className="space-y-5 rounded-card border border-line bg-surface p-8 shadow-card"
      data-testid="pairing"
      onSubmit={(e) => {
        e.preventDefault()
        void pair(code)
      }}
    >
      <h1 className="text-h2 font-bold">{t('pairing.title')}</h1>
      <p>{t('pairing.help')}</p>
      <label className="block text-label font-bold">
        {t('pairing.code')}
        <input
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          autoComplete="off"
          autoCapitalize="characters"
          maxLength={16}
          className="mt-2 block min-h-touch w-full rounded-ctl border-2 border-ink bg-surface px-4 font-mono text-h3 tracking-widest"
        />
      </label>
      {error && (
        <p role="alert" className="rounded-ctl bg-danger-soft p-4 font-bold text-danger">
          {error}
        </p>
      )}
      <Button
        type="submit"
        variant="primary"
        icon={Link2}
        disabled={busy || code.trim().length < 6}
      >
        {t('pairing.connect')}
      </Button>
    </form>
  )
}

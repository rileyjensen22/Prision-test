import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'
import { featureIcon } from '../icons'
import { ScreenFrame } from '../components'

const SOURCES = [
  { code: 'ocga', label: 'Official Code of Georgia Annotated (O.C.G.A.)' },
  { code: 'us_const', label: 'U.S. Constitution' },
  { code: 'ga_const', label: 'Georgia Constitution' },
  { code: 'prison_rules', label: 'Prison Litigation Reform Act (PLRA)' },
]

export function LawLibrary() {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const Icon = featureIcon('legal_materials')
  return (
    <ScreenFrame title={t('feature.legal_materials')} icon={Icon}>
      <div className="relative">
        <Search
          aria-hidden="true"
          className="absolute left-4 top-1/2 size-5 -translate-y-1/2 text-ink-soft"
        />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search Georgia law…"
          aria-label="Search Georgia law"
          className="w-full rounded-card border border-line bg-surface py-3 pl-12 pr-4 text-body focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <p className="mt-2 text-sm text-ink-soft">{t('stub.text')}</p>

      <ul className="mt-4 space-y-3">
        {SOURCES.map((s) => (
          <li key={s.code}>
            <button
              type="button"
              className="flex w-full min-h-touch items-center gap-4 rounded-card border border-line bg-surface p-4 text-left shadow-card hover:border-primary"
            >
              <span className="flex-1 text-label font-bold">{s.label}</span>
            </button>
          </li>
        ))}
      </ul>
    </ScreenFrame>
  )
}

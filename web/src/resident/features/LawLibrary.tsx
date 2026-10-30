import { useEffect, useState } from 'react'
import { BookOpen, ChevronRight, Search } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Card, ScreenFrame } from '../components'

interface LawSection {
  id: string
  title: string
  text: string
}

interface LawSource {
  id: string
  title: string
  sections: LawSection[]
}

const SOURCES = [
  { id: 'constitution', label: 'U.S. Constitution' },
  { id: 'plra', label: 'Prison Litigation Reform Act (PLRA)' },
  { id: 'declaration', label: 'Declaration of Independence' },
  { id: 'georgia', label: 'Georgia Law — Corrections' },
]

export function LawLibrary() {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [sourceId, setSourceId] = useState<string | null>(null)
  const [source, setSource] = useState<LawSource | null>(null)
  const [sectionId, setSectionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadErr, setLoadErr] = useState(false)

  useEffect(() => {
    if (!sourceId) { setSource(null); setSectionId(null); return }
    setLoading(true)
    setLoadErr(false)
    fetch(`/law/${sourceId}.json`)
      .then((r) => r.json())
      .then((data: LawSource) => {
        setSource(data)
        setSectionId(data.sections[0]?.id ?? null)
      })
      .catch(() => setLoadErr(true))
      .finally(() => setLoading(false))
  }, [sourceId])

  const sections = source?.sections ?? []
  const filtered = query
    ? sections.filter(
        (s) =>
          s.title.toLowerCase().includes(query.toLowerCase()) ||
          s.text.toLowerCase().includes(query.toLowerCase()),
      )
    : sections
  const activeSection = sections.find((s) => s.id === sectionId)

  return (
    <ScreenFrame title="Law Library">
      <Card className="border-l-4 border-l-primary bg-primary-soft p-4 text-sm">
        <strong>For informational purposes only. Not legal advice.</strong> If you need legal
        representation, contact an attorney through the Attorney Calls feature.
      </Card>

      {!sourceId ? (
        <div className="space-y-3">
          <h2 className="text-h3 font-bold">Select a source</h2>
          <ul className="space-y-2">
            {SOURCES.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => setSourceId(s.id)}
                  className="flex w-full min-h-touch items-center gap-4 rounded-card border border-line bg-surface p-4 text-left shadow-card hover:border-primary"
                >
                  <BookOpen aria-hidden="true" className="size-7 shrink-0 text-primary" strokeWidth={1.75} />
                  <span className="flex-1 text-label font-bold">{s.label}</span>
                  <ChevronRight aria-hidden="true" className="size-5 text-ink-soft" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <button
            type="button"
            onClick={() => { setSourceId(null); setQuery('') }}
            className="text-primary font-bold hover:underline"
          >
            ← Back to sources
          </button>

          <h2 className="text-h2 font-bold">{SOURCES.find((s) => s.id === sourceId)?.label}</h2>

          {loading && <p className="text-ink-soft">Loading…</p>}
          {loadErr && (
            <p role="alert" className="text-lock font-bold">
              Could not load this document. Please check your connection.
            </p>
          )}

          {source && (
            <div className="grid gap-4 lg:grid-cols-[18rem_1fr] lg:items-start">
              <div className="space-y-2">
                <div className="relative">
                  <Search
                    aria-hidden="true"
                    className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-soft"
                  />
                  <input
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search sections…"
                    aria-label="Search sections"
                    className="w-full rounded-ctl border border-line bg-surface py-2.5 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <ul className="max-h-[60vh] overflow-y-auto rounded-ctl border border-line divide-y divide-line">
                  {filtered.map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        onClick={() => { setSectionId(s.id); setQuery('') }}
                        className={`w-full px-3 py-2.5 text-left text-sm hover:bg-surface-2 ${
                          s.id === sectionId ? 'bg-primary-soft font-bold text-primary' : ''
                        }`}
                      >
                        {s.title}
                      </button>
                    </li>
                  ))}
                  {filtered.length === 0 && (
                    <li className="px-3 py-3 text-sm text-ink-soft">No sections match.</li>
                  )}
                </ul>
              </div>

              <Card className="min-h-[20rem] space-y-3">
                {activeSection ? (
                  <>
                    <h3 className="text-h3 font-bold">{activeSection.title}</h3>
                    <div className="prose prose-sm max-w-none whitespace-pre-wrap leading-relaxed text-body">
                      {activeSection.text}
                    </div>
                  </>
                ) : (
                  <p className="text-ink-soft">Select a section to read.</p>
                )}
              </Card>
            </div>
          )}
        </>
      )}
    </ScreenFrame>
  )
}

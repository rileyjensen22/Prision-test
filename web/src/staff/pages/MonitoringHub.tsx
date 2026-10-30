import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, Radio, ScrollText, Video } from 'lucide-react'
import { Page } from '../ui'
import Monitoring from './Monitoring'
import VideoOversight from './VideoOversight'
import Mirror from './Mirror'

const TABS = [
  { id: 'calls', label: 'Call monitoring', icon: Eye },
  { id: 'video', label: 'Video oversight', icon: Video },
  { id: 'mirror', label: 'Live mirror', icon: Radio },
  { id: 'log', label: 'Access log', icon: ScrollText },
] as const

type TabId = (typeof TABS)[number]['id']

function AccessLog() {
  const { t } = useTranslation()
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-soft">
        All monitoring and mirror access is logged here. Attorney calls are never recorded or
        monitored — this is a legal requirement.
      </p>
      <p className="text-ink-soft italic">
        Audit log filtered to monitoring events — coming in Phase 5 hardening.
      </p>
    </div>
  )
}

export default function MonitoringHub() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<TabId>('calls')

  return (
    <Page title="Monitoring Hub">
      <div
        role="tablist"
        aria-label="Monitoring tabs"
        className="flex gap-1 border-b border-line pb-1"
      >
        {TABS.map((tt) => (
          <button
            key={tt.id}
            role="tab"
            aria-selected={tab === tt.id}
            onClick={() => setTab(tt.id)}
            className={`flex items-center gap-2 rounded-t-ctl px-4 py-2.5 text-sm font-bold transition-colors ${
              tab === tt.id
                ? 'bg-primary text-primary-ink'
                : 'text-ink-soft hover:bg-surface-2 hover:text-ink'
            }`}
          >
            <tt.icon aria-hidden="true" className="size-4" />
            {tt.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === 'calls' && <Monitoring />}
        {tab === 'video' && <VideoOversight />}
        {tab === 'mirror' && <Mirror />}
        {tab === 'log' && <AccessLog />}
      </div>
    </Page>
  )
}

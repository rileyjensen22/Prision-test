import { AlertTriangle, Eye, Info, WifiOff, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from './cn'

type Tone = 'info' | 'notice' | 'offline' | 'simulation'

const TONE: Record<Tone, { cls: string; icon: LucideIcon }> = {
  info: { cls: 'bg-primary-soft text-ink border-primary', icon: Info },
  notice: { cls: 'bg-notice-soft text-notice border-notice', icon: AlertTriangle },
  offline: { cls: 'bg-notice-soft text-notice border-notice', icon: WifiOff },
  simulation: { cls: 'bg-danger text-primary-ink border-danger', icon: Eye },
}

/** A full-width status strip: icon plus words, so colour is never the only signal. */
export function Banner({
  tone = 'info',
  children,
  className,
  ...rest
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  role?: string
  'data-testid'?: string
}) {
  const { cls, icon: Icon } = TONE[tone]
  return (
    <div
      className={cn(
        'flex items-center justify-center gap-3 border-b-2 px-6 py-3 text-body font-bold',
        cls,
        className,
      )}
      {...rest}
    >
      <Icon aria-hidden="true" className="size-6 shrink-0" />
      <span>{children}</span>
    </div>
  )
}

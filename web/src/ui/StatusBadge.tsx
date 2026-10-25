import { AlertTriangle, CheckCircle2, Clock, Lock, WifiOff, type LucideIcon } from 'lucide-react'

import { cn } from './cn'

export type StatusTone = 'ok' | 'lock' | 'notice' | 'neutral' | 'offline'

const TONE: Record<StatusTone, { cls: string; icon: LucideIcon }> = {
  ok: { cls: 'bg-ok-soft text-ok', icon: CheckCircle2 },
  lock: { cls: 'bg-lock-soft text-lock', icon: Lock },
  notice: { cls: 'bg-notice-soft text-notice', icon: AlertTriangle },
  neutral: { cls: 'bg-surface-2 text-ink-soft', icon: Clock },
  offline: { cls: 'bg-surface-2 text-ink', icon: WifiOff },
}

/** Status is always icon + words, never colour alone. */
export function StatusBadge({
  tone,
  children,
  className,
}: {
  tone: StatusTone
  children: React.ReactNode
  className?: string
}) {
  const { cls, icon: Icon } = TONE[tone]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-bold',
        cls,
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-[1em] shrink-0" strokeWidth={2.5} />
      {children}
    </span>
  )
}

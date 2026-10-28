import { AlertTriangle, CheckCircle2, Info, type LucideIcon } from 'lucide-react'
import type { HTMLAttributes, ReactNode } from 'react'

import { cn } from './cn'

type Tone = 'ok' | 'notice' | 'danger' | 'info'

const TONE: Record<Tone, { cls: string; icon: LucideIcon }> = {
  ok: { cls: 'border-ok bg-ok-soft text-ink', icon: CheckCircle2 },
  notice: { cls: 'border-notice bg-notice-soft text-ink', icon: AlertTriangle },
  danger: { cls: 'border-danger bg-danger-soft text-ink', icon: AlertTriangle },
  info: { cls: 'border-primary bg-primary-soft text-ink', icon: Info },
}
const ICON_CLS: Record<Tone, string> = {
  ok: 'text-ok',
  notice: 'text-notice',
  danger: 'text-danger',
  info: 'text-primary',
}

/** An inline message: result of an action, a warning, or a note. Icon plus words, never colour alone. */
export function Notice({
  tone = 'info',
  children,
  className,
  ...rest
}: { tone?: Tone; children: ReactNode } & Omit<HTMLAttributes<HTMLDivElement>, 'children'>) {
  const { cls, icon: Icon } = TONE[tone]
  return (
    <div
      className={cn('flex items-start gap-3 rounded-card border-2 p-4 text-body', cls, className)}
      {...rest}
    >
      <Icon aria-hidden="true" className={cn('mt-0.5 size-7 shrink-0', ICON_CLS[tone])} />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

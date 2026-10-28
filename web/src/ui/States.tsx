import { Inbox, Loader2, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from './Button'
import { cn } from './cn'

function Block({
  icon: Icon,
  title,
  children,
  className,
  role,
}: {
  icon: LucideIcon
  title: string
  children?: ReactNode
  className?: string
  role?: string
}) {
  return (
    <div
      role={role}
      className={cn(
        'mx-auto flex max-w-xl flex-col items-center gap-4 rounded-card border border-dashed border-line bg-surface px-8 py-12 text-center',
        className,
      )}
    >
      <Icon aria-hidden="true" className="size-12 text-ink-soft" strokeWidth={1.75} />
      <p className="text-h3 font-bold">{title}</p>
      {children}
    </div>
  )
}

/** Nothing here yet. Say what it means and, where there is one, what to do next. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Block icon={Inbox} title={title}>
      {children && <div className="text-body text-ink-soft">{children}</div>}
    </Block>
  )
}

/** Something failed. Say what happened and offer the retry. */
export function ErrorState({
  title,
  children,
  onRetry,
}: {
  title: string
  children?: ReactNode
  onRetry?: () => void
}) {
  const { t } = useTranslation()
  return (
    <Block icon={TriangleAlert} title={title} role="alert">
      {children && <div className="text-body text-ink-soft">{children}</div>}
      {onRetry && (
        <Button variant="primary" onClick={onRetry}>
          {t('app.retry')}
        </Button>
      )}
    </Block>
  )
}

export function LoadingState({ title }: { title?: string }) {
  const { t } = useTranslation()
  return (
    <Block icon={Loader2} title={title ?? t('app.loading')} role="status">
      {null}
    </Block>
  )
}

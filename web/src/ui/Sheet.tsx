import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from './Button'

/**
 * A modal sheet on the native <dialog> element: focus trap, Escape and inert background come
 * from the browser, and it injects no styles at runtime (the kiosk CSP forbids that).
 */
export function Sheet({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const { t } = useTranslation()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (d && !d.open) d.showModal()
  }, [])
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      className="m-auto w-full max-w-2xl rounded-card border border-line bg-surface p-0 text-ink shadow-card backdrop:bg-black/60"
    >
      <div className="space-y-5 p-8">
        <div className="flex items-start justify-between gap-4">
          <h2 className="text-h2 font-bold">{title}</h2>
          <Button variant="secondary" icon={X} onClick={onClose}>
            {t('request.close')}
          </Button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

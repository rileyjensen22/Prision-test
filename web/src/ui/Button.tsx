import type { LucideIcon } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

import { cn } from './cn'

type Variant = 'primary' | 'secondary' | 'quiet' | 'danger'

const BASE =
  'inline-flex min-h-touch items-center justify-center gap-3 rounded-ctl px-6 py-3 text-label font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50'

const VARIANT: Record<Variant, string> = {
  primary: 'bg-primary text-primary-ink hover:brightness-110 active:brightness-95',
  secondary: 'border-2 border-ink bg-surface text-ink hover:bg-surface-2',
  quiet: 'text-primary underline underline-offset-4 hover:bg-primary-soft',
  danger: 'bg-danger text-primary-ink hover:brightness-110',
}

interface Common {
  variant?: Variant
  icon?: LucideIcon
  children: ReactNode
  className?: string
}

function Inner({ icon: Icon, children }: Pick<Common, 'icon' | 'children'>) {
  return (
    <>
      {Icon && <Icon aria-hidden="true" className="size-6 shrink-0" strokeWidth={2.25} />}
      <span>{children}</span>
    </>
  )
}

/** The one button. Always a text label; the icon is a reinforcement, never a replacement. */
export function Button({
  variant = 'secondary',
  icon,
  className,
  children,
  type = 'button',
  ...rest
}: Common & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children' | 'className'>) {
  return (
    <button type={type} className={cn(BASE, VARIANT[variant], className)} {...rest}>
      <Inner icon={icon}>{children}</Inner>
    </button>
  )
}

/** A link that looks and sizes like a Button. */
export function LinkButton({
  variant = 'secondary',
  icon,
  className,
  children,
  ...rest
}: Common & Omit<LinkProps, 'children' | 'className'>) {
  return (
    <Link className={cn(BASE, VARIANT[variant], className)} {...rest}>
      <Inner icon={icon}>{children}</Inner>
    </Link>
  )
}

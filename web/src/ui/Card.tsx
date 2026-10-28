import type { HTMLAttributes } from 'react'

import { cn } from './cn'

export function Card({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn('rounded-card border border-line bg-surface p-6 shadow-card', className)}
      {...rest}
    />
  )
}

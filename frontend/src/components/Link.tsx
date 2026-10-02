/**
 * A link that works with and without a router.
 *
 * Phase 8b accessibility: every interactive element is a real <a> or <button>,
 * so it is keyboard-focusable and announced correctly by default. No
 * onClick-on-a-div, which is the most common way a "link" ends up unusable
 * without a mouse.
 */
import { AnchorHTMLAttributes, ReactNode } from 'react'

type Props = AnchorHTMLAttributes<HTMLAnchorElement> & {
  href: string
  children: ReactNode
}

export function Link({ href, children, ...rest }: Props) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  )
}

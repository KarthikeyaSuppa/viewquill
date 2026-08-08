import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { useReducedMotion } from 'motion/react'
import { cn } from '@/lib/utils'

/**
 * Feature-detected once at module load, not per-mount — `animation-timeline: view()` support
 * is a browser capability that can't change mid-session, so there's no reason to re-run
 * `CSS.supports` on every render (or even on every mount). Guarded for non-browser/test
 * environments where `CSS` may not exist.
 */
const supportsViewTimeline: boolean =
  typeof CSS !== 'undefined' && typeof CSS.supports === 'function' && CSS.supports('animation-timeline: view()')

export interface ScrollHighlightProps {
  children: ReactNode
  /**
   * Optional hue (0–360, matches CSS `hsl()`/`oklch()` hue angle) for a one-off accent color
   * instead of the default primary-derived tint. Rendered as a mid-lightness `oklch()` value
   * — not a hardcoded light/dark pair — so it reads correctly across all four themes (Day,
   * Night, Sunset, Sunrise), the same posture the design system's own token blocks use
   * (`src/index.css`).
   */
  hue?: number
  /** Optional small floating tag rendered beside the highlight. Purely decorative — rendered
   * `aria-hidden` — and only mounted when a value is passed. */
  badge?: string
  className?: string
}

/**
 * A reusable scroll-reveal highlight: a `<mark>`-style colored highlight that wipes in
 * left→right as its text scrolls into view, with an optional accent badge.
 *
 * CHROME / app-authored text ONLY — never the manuscript reading surface or raw user prose
 * (docs/10-DESIGN-SYSTEM.md: "playfulness stays in UI chrome, never inside manuscript text").
 * Do not use this inside `manuscript-reader.tsx`, scene descriptions, or any other place the
 * user's own story text is rendered.
 *
 * Adapted from a reference that drives the wipe with `animation-timeline: view()`. That's
 * feature-detected once via `CSS.supports` (see `supportsViewTimeline` above); when it isn't
 * supported, an `IntersectionObserver` (threshold 1 — only fires once the element is fully in
 * view) mirrors the same reveal by setting the `--qn-highlighted` custom property the CSS
 * keyframe path also animates (0 → 1, and back to 0 when it leaves view), from a `useEffect`
 * with proper cleanup (`observer.disconnect()`) on unmount.
 *
 * Two-layer structure — a `<mark class="qn-highlight">` (kept transparent, so it never
 * double-paints and still reads correctly to assistive tech) wrapping an inner `<span>` that
 * actually carries the wipe — matches the reference's `mark` / `mark span` split exactly. See
 * the `.qn-highlight` block in `src/index.css` for the paired CSS.
 *
 * Under `prefers-reduced-motion: reduce`, the highlight renders in its final painted state
 * immediately — no animation, no `IntersectionObserver` at all.
 */
export function ScrollHighlight({ children, hue, badge, className }: ScrollHighlightProps) {
  // `motion/react`'s `useReducedMotion` is already the app-wide reduced-motion check (see
  // `lib/delight.ts`, `ink-edge.tsx`) — reused here rather than writing a second
  // `matchMedia('(prefers-reduced-motion: reduce)')` hook.
  const reduceMotion = useReducedMotion() ?? false
  const usesObserver = !reduceMotion && !supportsViewTimeline
  const wipeRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!usesObserver) return
    const el = wipeRef.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        el.style.setProperty('--qn-highlighted', entry.isIntersecting ? '1' : '0')
      },
      { threshold: 1 },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [usesObserver])

  const style: CSSProperties | undefined =
    hue !== undefined ? ({ '--qn-highlight-hue': `oklch(0.7 0.14 ${hue})` } as CSSProperties) : undefined

  return (
    <mark
      className={cn(
        'qn-highlight',
        reduceMotion ? 'qn-highlight--static' : supportsViewTimeline ? 'qn-highlight--view' : 'qn-highlight--observed',
        className,
      )}
      style={style}
    >
      <span ref={wipeRef}>{children}</span>
      {badge && (
        <span className="qn-highlight-badge" aria-hidden="true">
          {badge}
        </span>
      )}
    </mark>
  )
}

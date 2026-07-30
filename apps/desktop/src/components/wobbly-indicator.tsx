import { useCallback, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { useDelight } from '@/lib/delight'

/**
 * The freefrontend.com "wobbly underline menu" effect (PHASE-UI-EFFECTS.md #9), shared by
 * `app-shell.tsx`'s sidebar nav (vertical accent bar) and `book-screen.tsx`'s tab bar
 * (horizontal underline): a single bar that slides from the previously-active item to the
 * newly-active one, overshooting slightly past the target before settling — an elastic
 * "wobble" produced by one `cubic-bezier` transition, no animation library needed.
 *
 * Gated through `useDelight().motionOk` exactly like every other animated chrome element
 * (`firefly.tsx`, `lib/lottie.tsx`) — no separate/competing reduced-motion or delight-level
 * check. At `calm` or under `prefers-reduced-motion`, `motionOk` is false and the bar snaps
 * straight to the new position with `transition: none`; it never plays a toned-down wobble.
 *
 * Driven purely by which DOM element is "active" (`activeKey`/`activeElement`), so it slides
 * identically whether that change came from a mouse click or a keyboard-driven focus/selection
 * change (arrow-key tab navigation, Enter on a nav link) — there is no hover-only code path.
 */

export interface WobblyIndicatorProps {
  /** The positioned ancestor (`position: relative`) the indicator is measured and placed
   * within — callers pass the same ref they attach to their `<nav>`/`<TabsList>` element. */
  containerRef: RefObject<HTMLElement | null>
  /** The DOM node of the currently-active item, looked up by the caller (e.g. from a ref
   * map keyed by nav `to` or tab value). `null` while nothing resolves (e.g. current route
   * matches none of the nav items) — the indicator simply doesn't render. */
  activeElement: HTMLElement | null
  /** Identifies the active item so the effect re-measures on change; refs/DOM nodes aren't
   * reactive on their own. */
  activeKey: string
  orientation?: 'horizontal' | 'vertical'
  /** Tailwind classes for the bar's visual treatment (color, thickness, rounding) — layout
   * (position/size/transform) is computed inline and shouldn't be overridden here. */
  className?: string
}

interface IndicatorRect {
  offset: number
  size: number
}

export function WobblyIndicator({
  containerRef,
  activeElement,
  activeKey,
  orientation = 'horizontal',
  className,
}: WobblyIndicatorProps) {
  const { motionOk } = useDelight()
  const [rect, setRect] = useState<IndicatorRect | null>(null)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container || !activeElement) return

    function measure() {
      const containerBox = container!.getBoundingClientRect()
      const activeBox = activeElement!.getBoundingClientRect()
      setRect(
        orientation === 'horizontal'
          ? { offset: activeBox.left - containerBox.left, size: activeBox.width }
          : { offset: activeBox.top - containerBox.top, size: activeBox.height },
      )
    }

    measure()

    // Re-measure on resize/reflow (e.g. sidebar width or tab label wrapping changes) — the
    // bar shouldn't drift out of alignment with its target between active-item changes.
    const observer = new ResizeObserver(measure)
    observer.observe(container)
    observer.observe(activeElement)
    return () => observer.disconnect()
  }, [containerRef, activeElement, activeKey, orientation])

  if (!rect) return null

  const transform = orientation === 'horizontal' ? `translateX(${rect.offset}px)` : `translateY(${rect.offset}px)`

  return (
    <span
      aria-hidden="true"
      className={className}
      style={{
        position: 'absolute',
        ...(orientation === 'horizontal'
          ? { bottom: 0, left: 0, height: 2, width: rect.size }
          : { left: 0, top: 0, width: 2, height: rect.size }),
        transform,
        // The "wobble": an overshoot/back-ease cubic-bezier rather than a linear/ease-out
        // slide. `motionOk` is the sole gate — false collapses this to an instant snap.
        transition: motionOk ? 'transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)' : 'none',
        willChange: 'transform',
      }}
    />
  )
}

/** Tracks a map of DOM nodes keyed by item id (nav `to`, tab `value`, …) so callers can look
 * up "the currently-active element" by key without re-querying the DOM. Pair with
 * `<WobblyIndicator activeElement={refs.current.get(activeKey) ?? null} .../>`. */
export function useIndicatorRefs<Key extends string>() {
  const refs = useRef(new Map<Key, HTMLElement>())

  const setRef = useCallback(
    (key: Key) => (el: HTMLElement | null) => {
      if (el) refs.current.set(key, el)
      else refs.current.delete(key)
    },
    [],
  )

  return { refs, setRef }
}

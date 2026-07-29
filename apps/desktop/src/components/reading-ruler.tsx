import type { CSSProperties } from 'react'
import type { ReadingCursorPosition } from '@/lib/reading-cursor'
import { useDelight } from '@/lib/delight'

/** Mirrors `reading_ruler` in `app/services/settings_service.py` exactly — `off` renders
 * nothing, `grey_bar` highlights the current paragraph, `shade` dims everything else. */
export type ReadingRulerMode = 'off' | 'grey_bar' | 'shade'

const READING_RULER_MODES: ReadingRulerMode[] = ['off', 'grey_bar', 'shade']

/** Coerces the loosely-typed `settings.values['reading_ruler']` (`Record<string, unknown>`,
 * see `queries/settings.ts`) into a known mode, defaulting to `off` for anything unexpected —
 * e.g. before settings have loaded, or a value from a future/older backend. */
export function normalizeReadingRulerMode(value: unknown): ReadingRulerMode {
  return value === 'grey_bar' || value === 'shade' ? value : 'off'
}

/** `off -> grey_bar -> shade -> off`, per the task's cycle order. */
export function nextReadingRulerMode(mode: ReadingRulerMode): ReadingRulerMode {
  const currentIndex = READING_RULER_MODES.indexOf(mode)
  return READING_RULER_MODES[(currentIndex + 1) % READING_RULER_MODES.length]
}

interface ReadingRulerProps {
  /** The manuscript reader's own single `useReadingCursor` result — lifted up to the reader
   * so this overlay and focus mode share one hook call (and thus one mousemove/keydown
   * listener pair) rather than each attaching their own. Container must still be `position:
   * relative` (or otherwise establish a positioning context) so `top` lines up with
   * `useReadingCursor`'s container-relative measurements. */
  position: ReadingCursorPosition | null
  mode: ReadingRulerMode
}

/**
 * Purely visual overlay tracking `useReadingCursor`'s position (passed in by the reader) —
 * highlights (grey_bar) or isolates (shade) whichever paragraph the reader's mouse/arrow-key
 * attention is currently on. Never intercepts clicks or text selection (`pointer-events-none`)
 * and is invisible to assistive tech (`aria-hidden`), since it duplicates information already
 * present in the text itself. Renders nothing until `position` is known (the reader hasn't
 * moved the mouse/pressed an arrow key yet) or the mode is `off`.
 */
export function ReadingRuler({ position, mode }: ReadingRulerProps) {
  const { motionOk } = useDelight()

  if (mode === 'off' || !position) return null

  // Only `top`/`height` ever move here, so scoping the transition to those two properties
  // (rather than `transition-all`) keeps this cheap; `motionOk` disables it entirely so the
  // ruler snaps instantly under reduced-motion/'calm' delight, never smoothly slides.
  const transition = motionOk ? 'top 100ms ease-out, height 100ms ease-out' : 'none'

  if (mode === 'grey_bar') {
    const style: CSSProperties = {
      top: position.top,
      height: position.height,
      transition,
    }
    return (
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 rounded-md bg-foreground/10"
        style={style}
      />
    )
  }

  // 'shade': two translucent panels covering everything above and below the current
  // paragraph's band, so only that band reads at full contrast.
  const topPanelStyle: CSSProperties = {
    top: 0,
    height: position.top,
    transition: motionOk ? 'height 100ms ease-out' : 'none',
  }
  const bottomPanelStyle: CSSProperties = {
    top: position.top + position.height,
    bottom: 0,
    transition: motionOk ? 'top 100ms ease-out' : 'none',
  }

  return (
    <>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bg-background/75"
        style={topPanelStyle}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bg-background/75"
        style={bottomPanelStyle}
      />
    </>
  )
}

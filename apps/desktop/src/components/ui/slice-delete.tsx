import { useCallback, useRef, useState } from 'react'
import { useDelight } from '@/lib/delight'

/**
 * "Slice-to-delete" row/chip removal — a reference jQuery "sweep a blade across, then the
 * row collapses" effect, reimplemented in plain React state + CSS keyframes (see the
 * `.qn-slice-*` block in `src/index.css`). NO jQuery, NO Web Animations API needed — CSS
 * `animationend` plus a `setTimeout` fallback is enough here and keeps this file dependency-
 * free.
 *
 * Gated exactly like every other delight-tier animation in this app (docs/10 §8): only at
 * `delight_level === 'playful'` AND `prefers-reduced-motion: no-preference`. Anywhere else,
 * `startRemove()` fires the real mutation immediately — pixel-for-pixel today's behavior,
 * zero visual regression.
 *
 * CORRECTNESS: the caller's `onCommit` (the actual delete/unlink/detach mutation) is
 * GUARANTEED to fire exactly once, regardless of path:
 *   - not animating → fires synchronously inside `startRemove()`.
 *   - animating, animation completes normally → `onAnimationEnd` (wired to the row/chip's
 *     `onAnimationEnd` prop) fires it.
 *   - animating, but `animationend` never arrives (tab backgrounded, animation interrupted,
 *     the row/chip unmounts mid-animation for an unrelated reason, etc.) → the `setTimeout`
 *     fallback started alongside the animation fires it. Timers are plain JS, not tied to
 *     React's component tree, so this backstop still runs even after the component that
 *     started it has unmounted.
 *   - `committedRef` guards every path so `onCommit` never double-fires no matter which of
 *     the above wins the race, and `startRemove`/re-entrant calls while already
 *     removing/committed are no-ops.
 *
 * Deliberately does NOT clear the fallback timer on unmount — clearing it would reopen the
 * exact "mutation gets swallowed if the component unmounts mid-animation" bug this hook
 * exists to prevent.
 */

export type SliceDeleteVariant = 'row' | 'chip'

/** Matches the CSS animation duration set on `.qn-slice-row`/`.qn-slice-chip` in
 * `src/index.css` (600ms), plus a buffer so the fallback only ever wins the race when
 * `animationend` genuinely didn't fire. */
const SLICE_ANIMATION_MS = 600
const SLICE_FALLBACK_MS = SLICE_ANIMATION_MS + 150

export interface UseSliceDeleteResult {
  /** True from the moment `startRemove()` decides to animate until `onCommit` fires.
   * Caller should keep rendering the row/chip (do not early-return null) while this is
   * true — the CSS animation needs the element to stay in the DOM. */
  removing: boolean
  /** Call this from the same click handler that used to call the mutation directly (e.g.
   * inside an `AlertDialogAction onClick`, or a plain `onClick`). Decides animate-vs-instant
   * and always results in `onCommit` firing exactly once. */
  startRemove: () => void
  /** Wire to the row/chip element's `onAnimationEnd`. No-op if not currently removing or
   * already committed. */
  onAnimationEnd: () => void
  /** `true` only while actually animating (i.e. `removing && animate`) — lets a caller that
   * needs to branch (rather than just apply `className`) do so precisely. */
  animating: boolean
  /** Convenience class to spread onto the row/chip element while `removing` is true (applies
   * the matching `.qn-slice-row`/`.qn-slice-chip` keyframe block from `index.css`). Callers
   * that build their own `className` string can instead check `removing`/`animating` and the
   * `variant` they passed in directly — this is just the common case pre-computed. */
  className: string | undefined
}

/**
 * @param onCommit The real delete/unlink/detach mutation call (e.g. `() =>
 * deleteCodex.mutate(entry.id)`). Must be a stable-enough callback — it is only ever invoked
 * (at most once) from `startRemove`'s resulting animation-end/timeout/immediate path.
 * @param variant `'row'` (default) for text list rows — sweeping blade + collapse.
 * `'chip'` for circular chips/thumbnails — scale-out + fade only (no literal slice line).
 */
export function useSliceDelete(onCommit: () => void, variant: SliceDeleteVariant = 'row'): UseSliceDeleteResult {
  const { level, motionOk } = useDelight()
  const animate = level === 'playful' && motionOk

  const [removing, setRemoving] = useState(false)
  const committedRef = useRef(false)
  const fallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit

  const commit = useCallback(() => {
    if (committedRef.current) return
    committedRef.current = true
    if (fallbackTimerRef.current) {
      clearTimeout(fallbackTimerRef.current)
      fallbackTimerRef.current = null
    }
    onCommitRef.current()
  }, [])

  const startRemove = useCallback(() => {
    if (committedRef.current || removing) return
    if (!animate) {
      commit()
      return
    }
    setRemoving(true)
    // Belt-and-suspenders: guarantees `onCommit` fires even if `animationend` is missed
    // (backgrounded tab, interrupted animation, mid-animation unmount for an unrelated
    // reason — see file header). Intentionally NOT cleared on unmount.
    fallbackTimerRef.current = setTimeout(commit, SLICE_FALLBACK_MS)
  }, [animate, commit, removing])

  const onAnimationEnd = useCallback(() => {
    commit()
  }, [commit])

  return {
    removing,
    startRemove,
    onAnimationEnd,
    animating: removing && animate,
    className: removing && animate ? (variant === 'chip' ? 'qn-slice-chip' : 'qn-slice-row') : undefined,
  }
}

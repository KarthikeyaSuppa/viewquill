import { useEffect, useState } from 'react'
import { LottiePlayer } from '@/lib/lottie'
import { subscribeDelightAccent } from '@/lib/delight'

// assets/lottie/delight-accent.json: fr(frame rate)=30, ip(in point)=0, op(out point)=60 —
// a real play-through is (op - ip) / fr seconds = 60 / 30 = 2s. Computed once here from the
// asset's own fields (not guessed) rather than read at runtime, since the asset is static;
// keep this comment + constant in sync if the asset is ever swapped for a different length.
const ACCENT_DURATION_MS = 2000

/**
 * Mounted exactly once, app-wide (`components/providers.tsx`, alongside `<Toaster/>`).
 * Renders nothing until `useDelight().fireDelightAccent()` is called (see `lib/delight.ts`'s
 * `subscribeDelightAccent` pub/sub), then mounts the `delight-accent.json` Lottie loop
 * (`loop={false}`, one play-through) as a brief, non-interactive, centered overlay, and
 * unmounts it again after `ACCENT_DURATION_MS`. Mounting/unmounting per trigger (rather than
 * keeping one instance always-mounted-but-hidden) is what lets consecutive triggers actually
 * replay from frame 0 — lottie-react has no imperative "replay a non-looping animation"
 * call, only a fresh `useLottie` instance does.
 */
export function DelightAccentOverlay() {
  const [playKey, setPlayKey] = useState<number | null>(null)

  useEffect(() => subscribeDelightAccent(() => setPlayKey(Date.now())), [])

  useEffect(() => {
    if (playKey === null) return
    const timer = setTimeout(() => setPlayKey(null), ACCENT_DURATION_MS)
    return () => clearTimeout(timer)
  }, [playKey])

  if (playKey === null) return null

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center"
    >
      <LottiePlayer
        key={playKey}
        animationData={() => import('@/assets/lottie/delight-accent.json')}
        loop={false}
        className="size-24"
      />
    </div>
  )
}

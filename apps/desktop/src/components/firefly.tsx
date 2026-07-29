import { motion } from 'motion/react'
import { useThemeStore } from '@/stores/theme'
import { useDelight } from '@/lib/delight'
import { LottiePlayer } from '@/lib/lottie'

/**
 * A single ambient firefly (docs/10 §6, v1.0): a soft pulsing glow-orb (Lottie) that
 * drifts lazily around the screen. Night-only, decorative, and inert — never intercepts
 * input. The outer wrapper owns positioning/drift; `<LottiePlayer>` owns the glow look
 * itself. Motion/reduced-motion gating has a single source of truth — `useDelight().motionOk`
 * — used here for the drift and internally by `<LottiePlayer>` (which freezes the glow on
 * its first frame when motion isn't ok), so there's no separate/competing
 * `useReducedMotion` check.
 */
export function Firefly() {
  const theme = useThemeStore((s) => s.theme)
  const { motionOk } = useDelight()

  if (theme !== 'night') return null

  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none fixed z-0 size-2.5"
      style={{ top: '35%', left: '20%' }}
      animate={
        motionOk
          ? {
              x: [0, 60, 20, 90, 0],
              y: [0, -40, 30, -10, 0],
            }
          : undefined
      }
      transition={{
        duration: 24,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
    >
      <LottiePlayer
        animationData={() => import('../assets/lottie/mascot-idle.json')}
        loop
        ariaHidden
        className="size-2.5"
      />
    </motion.div>
  )
}

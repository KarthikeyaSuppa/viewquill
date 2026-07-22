import { motion, useReducedMotion } from 'motion/react'
import { useThemeStore } from '@/stores/theme'

/**
 * A single ambient firefly (docs/10 §6, v1.0): a soft gold glow that drifts lazily
 * around the screen. Night-only, decorative, and inert — never intercepts input.
 */
export function Firefly() {
  const theme = useThemeStore((s) => s.theme)
  const reduceMotion = useReducedMotion()

  if (theme !== 'night') return null

  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none fixed z-0 size-2.5 rounded-full"
      style={{
        top: '35%',
        left: '20%',
        background: 'oklch(0.8 0.15 90)',
        boxShadow: '0 0 12px 4px oklch(0.8 0.15 90 / 0.7)',
        filter: 'blur(1.5px)',
      }}
      animate={
        reduceMotion
          ? { opacity: [0.4, 0.9, 0.4] }
          : {
              x: [0, 60, 20, 90, 0],
              y: [0, -40, 30, -10, 0],
              opacity: [0.3, 0.9, 0.5, 0.8, 0.3],
            }
      }
      transition={{
        duration: 24,
        repeat: Infinity,
        ease: 'easeInOut',
      }}
    />
  )
}

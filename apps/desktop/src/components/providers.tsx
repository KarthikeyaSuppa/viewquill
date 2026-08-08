import type { ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { queryClient } from '@/queries/client'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { DelightAccentOverlay } from '@/lib/delight-accent'
import { useSyncSoundPrefs } from '@/lib/delight'

/** Keeps the module-level UI-sound cache (`playUiSound()` in `lib/delight.ts`) in sync with
 * live settings. Mounted once, inside `QueryClientProvider`, so `useSettings()` works. The
 * hook-free `button.tsx`/`tabs.tsx`/`dialog.tsx` primitives read that cache instead of each
 * calling `useSettings()`/`useDelight()` themselves. */
function SoundPrefsSync() {
  useSyncSoundPrefs()
  return null
}

/** App-wide providers: data fetching, tooltips, toasts, motion config. Mount once at the
 * root. `reducedMotion="user"` (docs/10 §8) makes every `motion.*` component across the
 * app automatically honor the OS `prefers-reduced-motion` preference without each one
 * needing its own check — the delight-level gating on top of that (calm/standard/playful)
 * is handled separately per-component via `useDelight()` (src/lib/delight.ts). */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <TooltipProvider>
          <SoundPrefsSync />
          {children}
          <Toaster richColors position="bottom-right" />
          <DelightAccentOverlay />
        </TooltipProvider>
      </MotionConfig>
    </QueryClientProvider>
  )
}

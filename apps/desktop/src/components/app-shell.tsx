import { useEffect, useRef } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Library, Settings } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { Firefly } from '@/components/firefly'
import { SettingsProvider } from '@/components/settings-provider'
import { ReadingComfortWizard } from '@/components/onboarding/reading-comfort-wizard'
import { useSettings } from '@/queries/settings'
import { useOnboardingWizardStore } from '@/stores/onboarding'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: 'Library', icon: Library, end: true },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
]

/**
 * App chrome (docs/10): a floating glass sidebar (wordmark, nav, theme toggle) around
 * a routed main area. Mounted once by the router as the top-level layout route.
 */
export function AppShell() {
  const location = useLocation()
  const reduceMotion = useReducedMotion()

  const { data: settingsValues, isSuccess: settingsLoaded } = useSettings()
  const openWizard = useOnboardingWizardStore((s) => s.open)
  const hasAutoOpened = useRef(false)

  // First-run gate (docs/10 §7): once settings have loaded, auto-open the wizard exactly
  // once if onboarding hasn't been completed yet.
  useEffect(() => {
    if (!settingsLoaded || hasAutoOpened.current) return
    if (settingsValues?.onboarding_complete !== true) {
      hasAutoOpened.current = true
      openWizard()
    }
  }, [settingsLoaded, settingsValues, openWizard])

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-background">
      <SettingsProvider />
      <ReadingComfortWizard />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            'radial-gradient(55% 45% at 10% 0%, oklch(0.54 0.21 277 / 0.12), transparent 70%)',
        }}
      />

      <Firefly />

      <aside className="glass glass-edge relative z-10 m-4 flex w-56 shrink-0 flex-col rounded-2xl p-4">
        <div className="px-2 pt-1 pb-6">
          <span className="text-lg font-semibold tracking-tight">Quillnight</span>
        </div>

        <nav className="flex flex-1 flex-col gap-1">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-muted-foreground transition-colors',
                  'hover:bg-accent hover:text-foreground',
                  isActive &&
                    'bg-primary/10 text-foreground ring-1 ring-primary/30 shadow-[0_0_16px_-2px_var(--primary)]',
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <ThemeToggle className="self-start" />
      </aside>

      <main className="relative z-10 min-w-0 flex-1 overflow-y-auto p-6">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={location.pathname}
            initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Library, LogOut, Search, Settings } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'
import { SettingsProvider } from '@/components/settings-provider'
import { ReadingComfortWizard } from '@/components/onboarding/reading-comfort-wizard'
import { HelpGuide } from '@/components/help/help-guide'
import { BackupNudge } from '@/components/backup-nudge'
import { SearchDialog } from '@/components/search/search-dialog'
import { Button } from '@/components/ui/button'
import { resolveAvatar } from '@/components/auth/avatars'
import { useSettings } from '@/queries/settings'
import { useLogout } from '@/queries/profiles'
import { useOnboardingWizardStore } from '@/stores/onboarding'
import { useAuthStore } from '@/stores/auth'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { to: '/', label: 'Library', icon: Library, end: true },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
]

/** Shared base styling for every sidebar nav entry — routed `NavLink`s add their own
 * `isActive` state on top of this; the Help trigger (not a route) uses it as-is. */
const NAV_ITEM_CLASS =
  'flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50'

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

  const currentUser = useAuthStore((s) => s.user)
  const logout = useLogout()
  const avatar = resolveAvatar(currentUser?.avatar)

  const [searchOpen, setSearchOpen] = useState(false)

  // First-run gate (docs/10 §7): once settings have loaded, auto-open the wizard exactly
  // once if onboarding hasn't been completed yet.
  useEffect(() => {
    if (!settingsLoaded || hasAutoOpened.current) return
    if (settingsValues?.onboarding_complete !== true) {
      hasAutoOpened.current = true
      openWizard()
    }
  }, [settingsLoaded, settingsValues, openWizard])

  // Global Ctrl/Cmd+K shortcut (Phase 10 task 6) opens the library search from anywhere in
  // the app shell, in addition to the always-visible sidebar button — a lightweight
  // discoverability nod short of a full command palette (none exists yet to extend).
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-xl focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground focus:shadow-lg focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        Skip to main content
      </a>
      <SettingsProvider />
      <ReadingComfortWizard />
      <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />

      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            'radial-gradient(55% 45% at 10% 0%, oklch(0.54 0.21 277 / 0.12), transparent 70%)',
        }}
      />

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
                  NAV_ITEM_CLASS,
                  isActive &&
                    'bg-primary/10 text-foreground ring-1 ring-primary/30 shadow-[0_0_16px_-2px_var(--primary)]',
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}

          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            className={cn(NAV_ITEM_CLASS, 'justify-between')}
          >
            <span className="flex items-center gap-2.5">
              <Search className="size-4" />
              Search
            </span>
            <kbd className="rounded border border-border/60 bg-muted px-1 py-0.5 text-[10px] font-medium text-muted-foreground">
              Ctrl K
            </kbd>
          </button>

          <HelpGuide triggerClassName={NAV_ITEM_CLASS} />
        </nav>

        <div className="flex items-center justify-between gap-2 border-t border-border/60 pt-3">
          <Button
            variant="ghost"
            size="sm"
            className="min-w-0 flex-1 justify-start gap-2 px-2"
            onClick={() => logout.mutate()}
            title="Switch profile"
          >
            <span className="text-base" role="img" aria-label={avatar.label}>
              {avatar.emoji}
            </span>
            <span className="truncate text-xs font-medium">
              {currentUser?.display_name || currentUser?.username || 'Switch profile'}
            </span>
            <LogOut className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
          </Button>
          <ThemeToggle />
        </div>
      </aside>

      <main id="main-content" tabIndex={-1} className="relative z-10 min-w-0 flex-1 overflow-y-auto p-6 outline-none">
        <BackupNudge />
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

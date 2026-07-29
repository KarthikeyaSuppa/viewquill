import { useEffect } from 'react'
import { useSettings } from '@/queries/settings'
import { applyBgTint, applyDelight, applyReadingVars, resolveTheme } from '@/lib/apply-settings'
import { useThemeStore } from '@/stores/theme'

/**
 * Applies live `app_settings` (docs/03) app-wide: the manuscript reading CSS vars, the
 * resolved Day/Night theme, and the delight level. Mounted once in AppShell so every
 * screen — and every future settings change — stays in sync. Renders nothing.
 */
const AUTO_RECHECK_INTERVAL_MS = 60_000

export function SettingsProvider() {
  const { data: values } = useSettings()
  const setTheme = useThemeStore((s) => s.setTheme)

  useEffect(() => {
    if (!values) return
    applyReadingVars(values)
    applyDelight(values.delight_level)
    const theme = resolveTheme(values.theme_mode)
    setTheme(theme)
    applyBgTint(values.bg_tint, theme)
  }, [values, setTheme])

  // 'auto' theme_mode depends on wall-clock time, not just the settings value, so it
  // needs its own periodic re-check (a poll + an immediate re-check on tab refocus,
  // in case a lot of time passed while the tab was hidden) — not just the effect above,
  // which only re-runs when `values` itself changes.
  useEffect(() => {
    if (values?.theme_mode !== 'auto') return

    const recheck = () => {
      const resolved = resolveTheme(values.theme_mode)
      if (useThemeStore.getState().theme !== resolved) {
        setTheme(resolved)
        applyBgTint(values.bg_tint, resolved)
      }
    }

    const intervalId = window.setInterval(recheck, AUTO_RECHECK_INTERVAL_MS)
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') recheck()
    }
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [values?.theme_mode, values?.bg_tint, setTheme])

  return null
}

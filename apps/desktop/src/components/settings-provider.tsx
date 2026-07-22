import { useEffect } from 'react'
import { useSettings } from '@/queries/settings'
import { applyDelight, applyReadingVars, resolveTheme } from '@/lib/apply-settings'
import { useThemeStore } from '@/stores/theme'

/**
 * Applies live `app_settings` (docs/03) app-wide: the manuscript reading CSS vars, the
 * resolved Day/Night theme, and the delight level. Mounted once in AppShell so every
 * screen — and every future settings change — stays in sync. Renders nothing.
 */
export function SettingsProvider() {
  const { data: values } = useSettings()
  const setTheme = useThemeStore((s) => s.setTheme)

  useEffect(() => {
    if (!values) return
    applyReadingVars(values)
    applyDelight(values.delight_level)
    setTheme(resolveTheme(values.theme_mode))
  }, [values, setTheme])

  return null
}

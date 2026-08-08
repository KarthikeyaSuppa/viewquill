import { useState } from 'react'
import { Check, Palette } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useUpdateSettings } from '@/queries/settings'
import { useThemeStore, type Theme } from '@/stores/theme'
import { cn } from '@/lib/utils'

/** The four key hexes per theme, used only to paint each tile's own mini preview below —
 * not the live token values (those live in index.css's `[data-theme='…']` blocks). */
const THEME_SWATCHES: Record<Theme, { bg: string; surface: string; text: string; primary: string }> = {
  day: { bg: '#FBF5E9', surface: '#FFFDF6', text: '#3A2E28', primary: '#C77D3A' },
  night: { bg: '#1E1E24', surface: '#27272F', text: '#DEE4EA', primary: '#FFC94D' },
  sunset: { bg: '#151C19', surface: '#2F3834', text: '#ECD2C5', primary: '#C0AB92' },
  sunrise: { bg: '#ECD2C5', surface: '#F3E8E5', text: '#4F2733', primary: '#8A3F56' },
}

const THEME_TILES: { value: Theme; label: string }[] = [
  { value: 'day', label: 'Day' },
  { value: 'night', label: 'Night' },
  { value: 'sunset', label: 'Sunset' },
  { value: 'sunrise', label: 'Sunrise' },
]

/** A single mini theme preview: outer surface fill → inset "card" → a text-color bar →
 * a primary-color dot. Purely decorative (aria-hidden) — the real label lives on the
 * enclosing button's `aria-label`. */
function ThemeSwatch({ theme }: { theme: Theme }) {
  const swatch = THEME_SWATCHES[theme]
  return (
    <div
      aria-hidden="true"
      className="flex h-14 w-full flex-col gap-1.5 rounded-lg p-2"
      style={{ backgroundColor: swatch.bg }}
    >
      <div className="flex-1 rounded-md p-1.5" style={{ backgroundColor: swatch.surface }}>
        <div className="h-1.5 w-2/3 rounded-full" style={{ backgroundColor: swatch.text }} />
      </div>
      <div className="size-2.5 rounded-full" style={{ backgroundColor: swatch.primary }} />
    </div>
  )
}

/**
 * Floating theme picker (docs/10): a glass icon button that opens a 2×2 grid of Day / Night
 * / Sunset / Sunrise preview tiles. Replaces the old plain Day/Night <ThemeToggle> in the
 * app shell footer (theme-toggle.tsx itself stays on disk — it's still used pre-login on
 * profile-gate.tsx/status-screen.tsx). Writes both the persisted setting (`theme_mode`, so
 * it survives a restart/other device) and the in-memory store (instant repaint, no round
 * trip to the backend needed to see the new theme).
 */
export function ThemePicker() {
  const [open, setOpen] = useState(false)
  const theme = useThemeStore((s) => s.theme)
  const updateSettings = useUpdateSettings()

  function choose(next: Theme) {
    useThemeStore.getState().setTheme(next)
    updateSettings.mutate({ theme_mode: next })
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="glass rounded-full" aria-label="Choose theme">
          <Palette className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent side="top" align="start" className="w-64">
        <div className="grid grid-cols-2 gap-2">
          {THEME_TILES.map((tile) => {
            const isActive = theme === tile.value
            return (
              <button
                key={tile.value}
                type="button"
                aria-label={`${tile.label} theme`}
                aria-pressed={isActive}
                onClick={() => choose(tile.value)}
                className={cn(
                  'relative flex flex-col gap-1 rounded-lg border border-border p-1 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50',
                  isActive && 'ring-2 ring-primary',
                )}
              >
                <ThemeSwatch theme={tile.value} />
                <span className="px-0.5 text-xs font-medium">{tile.label}</span>
                {isActive && (
                  <span className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full bg-primary text-primary-foreground">
                    <Check className="size-2.5" />
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}

import { create } from 'zustand'

/**
 * Four-theme chrome system (docs/10): Day/Night/Sunset/Sunrise. Persisted to localStorage
 * and mirrored onto <html> as `data-theme` (selects the token block in index.css) plus,
 * for the two dark-family themes, the `dark` class so Tailwind's `dark:` variant keeps
 * following it exactly as before — see index.css's `@custom-variant dark` + the
 * `[data-theme='…']` token blocks.
 */

export type Theme = 'day' | 'night' | 'sunset' | 'sunrise'

/** Dark-family themes — these (and only these) also get the `.dark` class. */
export const DARK_THEMES: ReadonlySet<Theme> = new Set(['night', 'sunset'])

const STORAGE_KEY = 'quillnight-theme'

function applyThemeClass(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.documentElement.classList.toggle('dark', DARK_THEMES.has(theme))
}

function readStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'day' || stored === 'night' || stored === 'sunset' || stored === 'sunrise' ? stored : 'night'
}

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggle: () => void
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: 'night',
  setTheme: (theme) => {
    localStorage.setItem(STORAGE_KEY, theme)
    applyThemeClass(theme)
    set({ theme })
  },
  // Still used by <ThemeToggle> (profile-gate.tsx, status-screen.tsx — pre-login/pre-settings
  // screens where the full 4-theme picker doesn't apply); simple day/night flip.
  toggle: () => {
    const next: Theme = get().theme === 'night' ? 'day' : 'night'
    get().setTheme(next)
  },
}))

/** Reads the persisted theme (defaulting to 'night') and applies it before first paint. */
export function initTheme() {
  const theme = readStoredTheme()
  applyThemeClass(theme)
  useThemeStore.setState({ theme })
}

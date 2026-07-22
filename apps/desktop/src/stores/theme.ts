import { create } from 'zustand'

/**
 * Day/Night chrome theme (docs/10). Persisted to localStorage and mirrored onto the
 * `dark` class on <html> so Tailwind's `dark:` variant follows it — see index.css.
 */

export type Theme = 'day' | 'night'

const STORAGE_KEY = 'quillnight-theme'

function applyThemeClass(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'night')
}

function readStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'day' || stored === 'night' ? stored : 'night'
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

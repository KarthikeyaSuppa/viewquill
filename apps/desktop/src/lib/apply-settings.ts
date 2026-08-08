import { DARK_THEMES, type Theme } from '@/stores/theme'

/**
 * Pure helpers that turn `app_settings` values (docs/03 + docs/10 §2) into live effects:
 * CSS vars on the manuscript surface, the resolved Day/Night theme, and the delight level.
 * No side effects other than the explicit DOM writes each function documents.
 */

/** Fontsource stacks (self-hosted, no CDN) keyed by the `font_family` setting value. */
export const FONT_STACKS: Record<string, string> = {
  Lexend: "'Lexend Variable', sans-serif",
  'Atkinson Hyperlegible Next': "'Atkinson Hyperlegible Next', sans-serif",
  OpenDyslexic: "'OpenDyslexic', sans-serif",
  Inter: "'Inter Variable', sans-serif",
  'System Serif': "Georgia, 'Times New Roman', serif",
}

/** BDA-guidance defaults (docs/10 §2) — also used as the slider default-tick markers. */
export const READING_DEFAULTS = {
  font_family: 'Lexend',
  font_size: 18,
  line_height: 1.5,
  letter_spacing: 0.035,
  line_length_ch: 65,
} as const

export interface ReadingValues {
  font_family?: unknown
  font_size?: unknown
  line_height?: unknown
  letter_spacing?: unknown
  line_length_ch?: unknown
}

/** Overwrites the `--reading-*` vars on `<html>` (index.css `:root`) from live settings. */
export function applyReadingVars(values: ReadingValues): void {
  const fontFamily = typeof values.font_family === 'string' ? values.font_family : READING_DEFAULTS.font_family
  const fontSize = typeof values.font_size === 'number' ? values.font_size : READING_DEFAULTS.font_size
  const lineHeight = typeof values.line_height === 'number' ? values.line_height : READING_DEFAULTS.line_height
  const letterSpacing =
    typeof values.letter_spacing === 'number' ? values.letter_spacing : READING_DEFAULTS.letter_spacing
  const lineLength =
    typeof values.line_length_ch === 'number' ? values.line_length_ch : READING_DEFAULTS.line_length_ch

  const root = document.documentElement.style
  root.setProperty('--reading-font', FONT_STACKS[fontFamily] ?? FONT_STACKS[READING_DEFAULTS.font_family])
  root.setProperty('--reading-size', `${fontSize}px`)
  root.setProperty('--reading-leading', `${lineHeight}`)
  root.setProperty('--reading-tracking', `${letterSpacing}em`)
  root.setProperty('--reading-measure', `${lineLength}ch`)
}

/**
 * Warm background-tint presets for the manuscript reading surface (docs/10 §1). Day values
 * are subtle variations close to the evidence-tuned cream base (`#fbf5e9`); Night values stay
 * at (or almost exactly at) the existing Night base (`#1e1e24`) — warmth is a Day-only
 * affordance, Night is never lightened.
 */
export const BG_TINTS: Record<'cream' | 'sand' | 'peach' | 'apricot', { day: string; night: string }> = {
  cream: { day: '#fbf5e9', night: '#1e1e24' },
  sand: { day: '#f7f0e0', night: '#1e1e24' },
  peach: { day: '#fbebe0', night: '#1f1e23' },
  apricot: { day: '#fce8d8', night: '#201e23' },
}

/** Overwrites `--manuscript-bg` (index.css `.manuscript`) from the `bg_tint` + resolved theme.
 * `BG_TINTS` only has a `day`/`night` column each (docs/10 §1 — warmth is a light-family-only
 * affordance); Sunset/Sunrise map onto whichever column matches their light/dark family. */
export function applyBgTint(value: unknown, theme: Theme): void {
  const key = value === 'cream' || value === 'sand' || value === 'peach' || value === 'apricot' ? value : 'cream'
  const col = DARK_THEMES.has(theme) ? 'night' : 'day'
  document.documentElement.style.setProperty('--manuscript-bg', BG_TINTS[key][col])
}

/** 'auto' resolves to Night between 18:00–05:59 local time, Day otherwise (docs/10 §1); any
 * of the four explicit themes (Day/Night/Sunset/Sunrise) resolve to themselves unchanged. */
export function resolveTheme(themeMode: unknown): Theme {
  if (themeMode === 'day' || themeMode === 'night' || themeMode === 'sunset' || themeMode === 'sunrise') {
    return themeMode
  }
  const hour = new Date().getHours()
  return hour >= 18 || hour < 6 ? 'night' : 'day'
}

export type DelightLevel = 'calm' | 'standard' | 'playful'

/** Mirrors the delight level onto `<html data-delight>` so CSS/JS can key off it (docs/10 §8). */
export function applyDelight(level: unknown): void {
  const value: DelightLevel = level === 'calm' || level === 'standard' || level === 'playful' ? level : 'playful'
  document.documentElement.dataset.delight = value
}

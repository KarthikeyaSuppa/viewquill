import { useEffect } from 'react'

/** True if `target` is somewhere a keystroke is meant to become text, not a shortcut —
 * inputs, textareas, and anything `contentEditable` (e.g. a rich-text field elsewhere on
 * the page). Reading shortcuts must never fire while the user is typing there. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
  )
}

/**
 * Registers a single-letter reading shortcut (no modifier keys) for the lifetime of the
 * calling component — i.e. only while a reading surface (manuscript reader / focus mode) is
 * actually mounted, never as an app-wide binding. Shared by the reading ruler's `R` and focus
 * mode's `F` so neither duplicates the "ignore modifier keys / ignore typing targets" guard.
 *
 * `enabled` additionally gates registration for cases where the surface is mounted but has
 * nothing to act on yet (e.g. the manuscript hasn't loaded/has no content) — pass `false` and
 * the listener is torn down (or never attached) until it flips back to `true`.
 */
export function useReadingShortcut(key: string, onTrigger: () => void, enabled = true): void {
  useEffect(() => {
    if (!enabled) return

    function handleKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key.toLowerCase() !== key.toLowerCase()) return
      if (isTypingTarget(event.target)) return
      onTrigger()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [key, onTrigger, enabled])
}

import { useMemo } from 'react'
import { useReducedMotion } from 'motion/react'
import confetti from 'canvas-confetti'
import { useSettings } from '@/queries/settings'
import { type DelightLevel } from '@/lib/apply-settings'

/**
 * The "delight base" (docs/10 §5, §8). A single readable helper so every consumer — view
 * transitions, the ink-edge pulse, confetti, sounds, the ambient firefly, the word
 * ticker — gates itself the same way: respect `prefers-reduced-motion` first, then the
 * user's `delight_level` setting. The manuscript reading surface never reads this module;
 * decoration lives in the chrome/canvas only.
 */

function normalizeDelight(level: unknown): DelightLevel {
  return level === 'calm' || level === 'standard' || level === 'playful' ? level : 'playful'
}

// ── Delight accent (one-shot Lottie) pub/sub ───────────────────────────────────────────
// `fireDelightAccent` (below) is called from the same call sites as `fireConfetti`, but
// unlike confetti (which `canvas-confetti` renders on its own full-page canvas), the Lottie
// accent needs a real DOM node to mount into. Rather than have every call site render its
// own `<LottiePlayer>`, one `<DelightAccentOverlay/>` (lib/delight-accent.tsx) is mounted
// once app-wide (in `components/providers.tsx`, alongside `<Toaster/>`) and subscribes here;
// this Set is the only link between the two, so `fireDelightAccent` can be called from a
// plain event handler with no overlay component in scope.
type AccentListener = () => void
const accentListeners = new Set<AccentListener>()

/** Internal — `lib/delight-accent.tsx`'s overlay is the only intended subscriber. */
export function subscribeDelightAccent(listener: AccentListener): () => void {
  accentListeners.add(listener)
  return () => {
    accentListeners.delete(listener)
  }
}

export interface Delight {
  level: DelightLevel
  /** False under reduced-motion OR at 'calm'. Gates view transitions, the ink-edge flow
   * animation, and the ambient firefly. */
  motionOk: boolean
  /** False unless `sounds_enabled` AND delight_level === 'playful' AND motion is allowed.
   * Callers must check this before calling any of the WebAudio helpers below — those
   * helpers are pure sound generators and do not re-check settings themselves, so this
   * flag is the single source of truth. */
  soundsOk: boolean
  /** Fires confetti for the given milestone. 'standard' only fires for `major`
   * milestones; 'playful' fires for all of them; 'calm' and reduced-motion never fire
   * (canvas-confetti's own `disableForReducedMotion` is a second backstop). */
  fireConfetti: (opts?: { major?: boolean }) => void
  /** Plays a brief one-shot Lottie accent (`assets/lottie/delight-accent.json`) alongside
   * confetti. 'playful' only — unlike `fireConfetti`, there is no `major`-only carve-out at
   * 'standard'; 'standard' stays confetti-only per the delight plan. No-op if
   * `<DelightAccentOverlay/>` isn't mounted (it always is, in `components/providers.tsx`),
   * and no-op under reduced-motion/'calm' same as confetti. */
  fireDelightAccent: () => void
}

export function useDelight(): Delight {
  const { data: settings } = useSettings()
  const reduceMotion = useReducedMotion() ?? false
  const level = normalizeDelight(settings?.delight_level)
  const soundsEnabled = settings?.sounds_enabled !== false

  return useMemo(() => {
    const motionOk = level !== 'calm' && !reduceMotion
    const confettiAllowed = level !== 'calm' && !reduceMotion
    const soundsOk = soundsEnabled && level === 'playful' && !reduceMotion

    function fireConfetti(opts: { major?: boolean } = {}) {
      if (!confettiAllowed) return
      const major = opts.major ?? false
      if (level === 'standard' && !major) return
      void confetti({
        particleCount: major ? 140 : 70,
        spread: major ? 90 : 65,
        startVelocity: 32,
        origin: { y: 0.7 },
        disableForReducedMotion: true,
      })
    }

    function fireDelightAccent() {
      if (level !== 'playful' || !motionOk) return
      accentListeners.forEach((listener) => listener())
    }

    return { level, motionOk, soundsOk, fireConfetti, fireDelightAccent }
  }, [level, reduceMotion, soundsEnabled])
}

// ── Asset-free sounds (Web Audio API) ──────────────────────────────────────────────────
// No audio files ship with the app — every sound below is a tiny oscillator + gain-envelope
// blip synthesized on demand, so nothing 404s and nothing bloats the bundle. `use-sound` is
// installed but deliberately unused for this: it expects a real audio asset URL, and we'd
// rather have zero sound assets to keep track of (and zero risk of a missing-file console
// error) than wire it to a data: URL. Every helper here is ≤300ms and quiet by design;
// gate every call site behind `useDelight().soundsOk` — these functions do not re-check
// settings themselves.

let sharedAudioContext: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  if (!sharedAudioContext) sharedAudioContext = new Ctor()
  return sharedAudioContext
}

/** One short sine blip with an exponential attack/decay envelope — the shared primitive
 * behind every sound below. `durationMs` is the full audible length (≤300ms per caller). */
function playTone(freqStart: number, freqEnd: number, durationMs: number, peakGain: number): void {
  const ctx = getAudioContext()
  if (!ctx) return

  const now = ctx.currentTime
  const durationSec = durationMs / 1000

  const oscillator = ctx.createOscillator()
  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(freqStart, now)
  oscillator.frequency.linearRampToValueAtTime(freqEnd, now + durationSec)

  const gain = ctx.createGain()
  gain.gain.setValueAtTime(0.0001, now)
  gain.gain.exponentialRampToValueAtTime(peakGain, now + Math.min(0.02, durationSec / 3))
  gain.gain.exponentialRampToValueAtTime(0.0001, now + durationSec)

  oscillator.connect(gain)
  gain.connect(ctx.destination)
  oscillator.start(now)
  oscillator.stop(now + durationSec + 0.02)
}

/** A soft rising chime — Enhance Accept. ~220ms. */
export function playChime(): void {
  playTone(880, 1320, 220, 0.05)
}

/** A brief falling swoosh — Book tab switch ("page turn"). ~160ms. */
export function playPageTurn(): void {
  playTone(320, 190, 160, 0.045)
}

/** One tick of a "scribbling" texture — meant to be called on a short interval while an
 * Enhance stream is in flight (see `startScribbleLoop`/`stopScribbleLoop`). ~70ms. */
export function playScribble(): void {
  const jitter = Math.random() * 120
  playTone(480 + jitter, 400 + jitter, 70, 0.022)
}

let scribbleTimer: ReturnType<typeof setInterval> | null = null

/** Starts a `playScribble()` loop (idempotent — a second call while already running is a
 * no-op). Caller is responsible for gating on `soundsOk` before starting, and must call
 * `stopScribbleLoop()` when the Enhance stream ends/errors/is cancelled. */
export function startScribbleLoop(): void {
  if (scribbleTimer) return
  scribbleTimer = setInterval(playScribble, 150)
}

export function stopScribbleLoop(): void {
  if (scribbleTimer) {
    clearInterval(scribbleTimer)
    scribbleTimer = null
  }
}

// ── First-node confetti (one-time milestone) ───────────────────────────────────────────

const FIRST_NODE_FLAG_KEY = 'quillnight_first_node_done'

/** True the very first time this is called (and persists that fact); false forever after. */
export function isFirstNodeMilestone(): boolean {
  if (typeof window === 'undefined') return false
  if (window.localStorage.getItem(FIRST_NODE_FLAG_KEY) === '1') return false
  window.localStorage.setItem(FIRST_NODE_FLAG_KEY, '1')
  return true
}

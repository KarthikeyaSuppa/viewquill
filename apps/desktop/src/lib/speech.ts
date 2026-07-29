/**
 * Read-aloud wrapper over the Web Speech API (`speechSynthesis`).
 *
 * LOCAL-FIRST HARD RULE (docs/02, CLAUDE.md): manuscript text must never leave the device.
 * Some Chromium/WebView2 voices (e.g. Microsoft "Natural" voices) stream text to a cloud
 * endpoint to synthesize speech. This file therefore only ever selects/uses voices where
 * `voice.localService === true`, and NEVER falls back to a remote voice — if no local voice
 * is available, speech is treated as unavailable and `speechSynthesis.speak()` is never called.
 */

import { tokenizeWords, type WordToken } from '@/lib/tokenize-words'

/** How long to wait for the async `voiceschanged` event before giving up on the current list. */
const VOICE_LOAD_TIMEOUT_MS = 1000

/**
 * Some browsers can briefly misbehave if `speak()` is called immediately after `cancel()`
 * (a known Web Speech API race) — this is the minimum gap we enforce after a cancel before
 * queuing new utterances.
 */
const POST_CANCEL_GUARD_MS = 60

let lastCancelAt = 0

function getSynth(): SpeechSynthesis | null {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return null
  return window.speechSynthesis
}

function filterLocal(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  return voices.filter((v) => v.localService === true)
}

/**
 * Resolves once the browser's voice list has (probably) finished loading, filtered to
 * ONLY `localService === true` voices. `getVoices()` can synchronously return `[]` on
 * first call in many browsers — voices load asynchronously, so this listens for
 * `voiceschanged` with a timeout fallback in case that event never fires.
 */
export function getLocalVoices(): Promise<SpeechSynthesisVoice[]> {
  const synth = getSynth()
  if (!synth) return Promise.resolve([])

  const initial = synth.getVoices()
  if (initial.length > 0) {
    return Promise.resolve(filterLocal(initial))
  }

  return new Promise((resolve) => {
    let settled = false
    let timer: ReturnType<typeof setTimeout>

    const finish = (voices: SpeechSynthesisVoice[]) => {
      if (settled) return
      settled = true
      synth.removeEventListener('voiceschanged', onVoicesChanged)
      clearTimeout(timer)
      resolve(filterLocal(voices))
    }

    const onVoicesChanged = () => finish(synth.getVoices())

    synth.addEventListener('voiceschanged', onVoicesChanged)
    timer = setTimeout(() => finish(synth.getVoices()), VOICE_LOAD_TIMEOUT_MS)
  })
}

/** Whether read-aloud can be offered at all right now (i.e. at least one local voice exists). */
export async function isSpeechAvailable(): Promise<boolean> {
  const voices = await getLocalVoices()
  return voices.length > 0
}

/**
 * Picks the voice to speak with, never returning a remote voice.
 *
 * - If `voiceURI` is given and matches a local voice, use it.
 * - Otherwise, use the browser's current default voice ONLY if that default is itself local.
 * - If a specific `voiceURI` was requested but not found among local voices, and the
 *   default isn't local either, return `null` (unavailable) — never guess a substitute.
 * - If no `voiceURI` was requested at all, any confirmed-local voice is an acceptable choice.
 */
function resolveVoice(
  synth: SpeechSynthesis,
  localVoices: SpeechSynthesisVoice[],
  voiceURI: string | undefined,
): SpeechSynthesisVoice | null {
  if (voiceURI) {
    const match = localVoices.find((v) => v.voiceURI === voiceURI)
    if (match) return match
  }

  const def = synth.getVoices().find((v) => v.default)
  if (def && def.localService) {
    return localVoices.find((v) => v.voiceURI === def.voiceURI) ?? def
  }

  if (!voiceURI) {
    // No specific voice was requested — any confirmed-local voice is fine.
    return localVoices[0] ?? null
  }

  // A specific (unavailable-locally) voice was requested and the default isn't local
  // either — do not substitute a remote voice under any circumstance.
  return null
}

/** Finds the word containing (or starting at/after) `charIndex` and returns its start offset. */
function findWordStart(words: WordToken[], charIndex: number): number {
  for (const w of words) {
    if (charIndex >= w.start && charIndex < w.end) return w.start
  }
  const next = words.find((w) => w.start >= charIndex)
  if (next) return next.start
  return words.length > 0 ? words[words.length - 1].start : 0
}

export interface SpeakOptions {
  voiceURI?: string
  rate?: number
  onBoundary?: (paraIndex: number, charIndex: number) => void
  onParagraphStart?: (paraIndex: number) => void
  onEnd?: () => void
}

export interface SpeechController {
  pause(): void
  resume(): void
  cancel(): void
}

/**
 * Speaks `paragraphs` one `SpeechSynthesisUtterance` per paragraph, using ONLY a local voice.
 * If zero local voices are available (or a requested voice can't be safely resolved to a
 * local one), this is a no-op that immediately fires `onEnd` — `speechSynthesis.speak()` is
 * never called. Use `isSpeechAvailable()`/`getLocalVoices()` beforehand to drive UI state.
 */
export function speak(paragraphs: string[], opts: SpeakOptions = {}): SpeechController {
  let cancelled = false
  const synth = getSynth()

  const controller: SpeechController = {
    pause() {
      if (cancelled || !synth) return
      synth.pause()
    },
    resume() {
      if (cancelled || !synth) return
      synth.resume()
    },
    cancel() {
      if (cancelled) return
      cancelled = true
      if (synth) {
        synth.cancel()
        lastCancelAt = Date.now()
      }
    },
  }

  if (!synth) {
    queueMicrotask(() => {
      if (!cancelled) opts.onEnd?.()
    })
    return controller
  }

  void (async () => {
    const localVoices = await getLocalVoices()
    if (cancelled) return

    if (localVoices.length === 0) {
      opts.onEnd?.()
      return
    }

    if (paragraphs.length === 0) {
      opts.onEnd?.()
      return
    }

    const voice = resolveVoice(synth, localVoices, opts.voiceURI)
    if (!voice) {
      // Could not resolve any local voice for this request — never fall back to remote.
      opts.onEnd?.()
      return
    }

    // Guard against the known "speak() right after cancel()" race.
    const sinceCancel = Date.now() - lastCancelAt
    if (sinceCancel >= 0 && sinceCancel < POST_CANCEL_GUARD_MS) {
      await new Promise((resolve) => setTimeout(resolve, POST_CANCEL_GUARD_MS - sinceCancel))
      if (cancelled) return
    }

    const rate = opts.rate ?? 1.0

    paragraphs.forEach((paragraph, paraIndex) => {
      const utterance = new SpeechSynthesisUtterance(paragraph)
      utterance.voice = voice
      utterance.rate = rate

      const words = tokenizeWords(paragraph)

      utterance.onstart = () => {
        if (cancelled) return
        opts.onParagraphStart?.(paraIndex)
      }

      utterance.onboundary = (event) => {
        if (cancelled) return
        // Some browsers omit `name`, others report non-word boundaries (e.g. "sentence") —
        // only act on word boundaries (or when `name` isn't reported at all). `charLength`
        // is unreliable (often 0) across browsers, so only `charIndex` is used here.
        if (event.name && event.name !== 'word') return
        const wordStart = findWordStart(words, event.charIndex)
        opts.onBoundary?.(paraIndex, wordStart)
      }

      if (paraIndex === paragraphs.length - 1) {
        utterance.onend = () => {
          if (cancelled) return
          opts.onEnd?.()
        }
        utterance.onerror = () => {
          if (cancelled) return
          opts.onEnd?.()
        }
      }

      synth.speak(utterance)
    })
  })()

  return controller
}

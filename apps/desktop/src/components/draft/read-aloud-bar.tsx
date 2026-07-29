import { useEffect, useRef, useState, type RefObject } from 'react'
import { Play, Pause, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSettings } from '@/queries/settings'
import { useDelight } from '@/lib/delight'
import { isSpeechAvailable, speak, type SpeechController } from '@/lib/speech'

/** DOM class toggled onto the currently-spoken word — see `.read-aloud-highlight` in
 * `index.css`. A flat background-color only, no transition/animation on the word itself
 * (docs/10-DESIGN-SYSTEM.md: "playfulness stays in UI chrome, never inside manuscript text"). */
const HIGHLIGHT_CLASS = 'read-aloud-highlight'

type PlaybackState = 'idle' | 'playing' | 'paused'

interface ReadAloudBarProps {
  /**
   * Raw paragraph strings, in the exact same order — and with the exact same blank-paragraph
   * exclusions — as `manuscript-reader.tsx`'s `tokenizeDocument` assigns its globally
   * sequential `paraIndex`/`data-para-index`. `speak()` (lib/speech.ts) reports back a
   * `paraIndex` that is simply this array's own index (`paragraphs.forEach((p, paraIndex) =>
   * ...)`), so as long as this array is built the same way manuscript-reader built its
   * `data-para-index` numbering, the two line up 1:1 with no offset/remap needed. See
   * `TokenizedParagraph.text`'s doc comment in manuscript-reader.tsx for how the caller
   * constructs this array.
   */
  paragraphs: string[]
  /** The manuscript reader's `data-reading-surface` container — read-aloud looks up
   * `p[data-para-index]` and `span[data-c]` within this element to place the highlight. */
  containerRef: RefObject<HTMLDivElement | null>
}

/**
 * Read-aloud toolbar (docs/06 Phase 8): Play/Pause/Stop over the Web Speech API wrapper in
 * `lib/speech.ts`, plus a karaoke-style word highlight synced off `speak()`'s `onBoundary`
 * callback. `charIndex` from `onBoundary` is already a word's *start* offset within its
 * paragraph (same convention as this reader's own `data-c`, both built from the shared
 * `tokenizeWords`/`WORD_RE` logic) — so locating the target span is a direct attribute lookup,
 * never a re-tokenize or an approximate scan.
 *
 * No `aria-live` region is added here or on the reading surface — the spoken audio itself is
 * the announcement; a duplicate live region would just cause screen readers to also read the
 * highlighted text, which is not the intent.
 */
export function ReadAloudBar({ paragraphs, containerRef }: ReadAloudBarProps) {
  const { data: settings } = useSettings()
  const { motionOk } = useDelight()

  // `null` while the initial local-voice probe is in flight — deliberately renders the same
  // (disabled) controls as `false` in the meantime, so there's no layout flash once it resolves.
  const [available, setAvailable] = useState<boolean | null>(null)
  const [state, setState] = useState<PlaybackState>('idle')
  const controllerRef = useRef<SpeechController | null>(null)
  const highlightedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let cancelled = false
    void isSpeechAvailable().then((ok) => {
      if (!cancelled) setAvailable(ok)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // If this bar unmounts mid-playback (e.g. the reader panel is hidden while reading aloud),
  // stop speech immediately rather than leaving an orphaned utterance running.
  useEffect(() => {
    return () => {
      controllerRef.current?.cancel()
      clearHighlight()
    }
    // Intentionally empty deps — this is unmount-only cleanup, not a per-render effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function clearHighlight() {
    highlightedRef.current?.classList.remove(HIGHLIGHT_CLASS)
    highlightedRef.current = null
  }

  function handleBoundary(paraIndex: number, charIndex: number) {
    clearHighlight()
    const container = containerRef.current
    if (!container) return
    const paragraphEl = container.querySelector<HTMLElement>(`p[data-para-index="${paraIndex}"]`)
    if (!paragraphEl) return
    const wordEl = paragraphEl.querySelector<HTMLElement>(`span[data-c="${charIndex}"]`)
    if (!wordEl) return
    wordEl.classList.add(HIGHLIGHT_CLASS)
    highlightedRef.current = wordEl
    wordEl.scrollIntoView({ block: 'nearest', behavior: motionOk ? 'smooth' : 'auto' })
  }

  function handlePlay() {
    if (state === 'paused') {
      controllerRef.current?.resume()
      setState('playing')
      return
    }
    if (paragraphs.length === 0) return

    const voiceURI = typeof settings?.tts_voice === 'string' ? settings.tts_voice : undefined
    const rate = typeof settings?.tts_rate === 'number' ? settings.tts_rate : undefined

    controllerRef.current = speak(paragraphs, {
      voiceURI,
      rate,
      onBoundary: handleBoundary,
      // Belt-and-suspenders: clears any highlight left over from the previous paragraph the
      // instant a new one starts, in case its first `onBoundary` is ever missed by a browser.
      onParagraphStart: clearHighlight,
      onEnd: () => {
        clearHighlight()
        controllerRef.current = null
        setState('idle')
      },
    })
    setState('playing')
  }

  function handlePause() {
    controllerRef.current?.pause()
    setState('paused')
  }

  function handleStop() {
    controllerRef.current?.cancel()
    controllerRef.current = null
    // Stop clears the highlight instantly — no fade-out.
    clearHighlight()
    setState('idle')
  }

  if (available === false) {
    return (
      <p className="text-xs text-muted-foreground" data-read-aloud-bar>
        Read-aloud isn&apos;t available on this device — no local voice is installed.
      </p>
    )
  }

  const playDisabled = available !== true || paragraphs.length === 0

  return (
    <div className="flex items-center gap-1.5" data-read-aloud-bar>
      <Button
        size="sm"
        variant="outline"
        disabled={playDisabled || state === 'playing'}
        onClick={handlePlay}
      >
        <Play className="size-3.5" />
        {state === 'paused' ? 'Resume' : 'Play'}
      </Button>
      <Button size="sm" variant="outline" disabled={state !== 'playing'} onClick={handlePause}>
        <Pause className="size-3.5" />
        Pause
      </Button>
      <Button size="sm" variant="outline" disabled={state === 'idle'} onClick={handleStop}>
        <Square className="size-3.5" />
        Stop
      </Button>
    </div>
  )
}

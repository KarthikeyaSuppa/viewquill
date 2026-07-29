import { useRef, type CSSProperties, type ReactNode } from 'react'
import { useDraftPreview, type CompiledChapterPreviewOut } from '@/queries/draft-preview'
import { useSettings, useUpdateSettings } from '@/queries/settings'
import { useReadingShortcut } from '@/lib/reading-shortcuts'
import { useReadingCursor } from '@/lib/reading-cursor'
import { useDelight } from '@/lib/delight'
import { cn } from '@/lib/utils'
import { LottiePlayer } from '@/lib/lottie'
import {
  ReadingRuler,
  normalizeReadingRulerMode,
  nextReadingRulerMode,
} from '@/components/reading-ruler'
import { ReadAloudBar } from '@/components/draft/read-aloud-bar'

interface ManuscriptReaderProps {
  bookId: string
}

interface TokenizedWord {
  word: string
  /** Globally sequential across the whole document — never resets per paragraph. */
  wordIndex: number
  /** Character offset of this word's first character within its own paragraph's raw text
   * (the exact string handed to the tokenizer below, before any splitting/trimming). Later
   * tasks (Speech API boundary-event mapping) depend on this being exact, not approximate. */
  charOffset: number
}

interface TokenizedParagraph {
  key: string
  /** Globally sequential across the whole document — never resets per chapter/scene. */
  paraIndex: number
  words: TokenizedWord[]
  /** This paragraph's raw text (the exact string tokenized above). Read-aloud
   * (`read-aloud-bar.tsx`) hands an array of these — in `paraIndex` order, with blank
   * paragraphs already excluded — straight to `speak()`, so `speak()`'s own per-paragraph
   * array index lines up exactly with this `paraIndex` / the rendered `data-para-index`. */
  text: string
}

interface TokenizedChapter {
  key: string
  title: string | null
  paragraphs: TokenizedParagraph[]
}

// Any run of non-whitespace is a "word" — whitespace (space, tab, newline) is always the
// separator. `matchAll` on a global regex hands back each match's `.index`, which is exactly
// the character offset of that word's first character within the string being scanned — no
// manual counting/approximation, so this can't drift out of sync with the raw text.
const WORD_RE = /\S+/g

/** One paragraph's raw text is a scene's prose split on blank lines (matching
 * `export_markdown.py`'s "existing paragraph breaks preserved" contract for `description`),
 * or — for script-type Books — one screenplay element's text per paragraph. Either way, the
 * string handed to `tokenizeParagraph` below IS the paragraph's raw text, so `match.index`
 * from it is already the correct `data-c` value with no further adjustment needed. */
function tokenizeParagraph(raw: string, nextWordIndex: () => number): TokenizedWord[] {
  const words: TokenizedWord[] = []
  for (const match of raw.matchAll(WORD_RE)) {
    words.push({
      word: match[0],
      wordIndex: nextWordIndex(),
      charOffset: match.index ?? 0,
    })
  }
  return words
}

function tokenizeDocument(chapters: CompiledChapterPreviewOut[]): TokenizedChapter[] {
  let paraIndex = 0
  let wordIndex = 0
  const nextWordIndex = () => wordIndex++

  return chapters.map((chapter, chapterIdx) => {
    const paragraphs: TokenizedParagraph[] = []

    chapter.scenes.forEach((scene, sceneIdx) => {
      const rawParagraphs =
        scene.elements.length > 0
          ? scene.elements.map((el) => el.text ?? '')
          : (scene.description ?? '').split(/\n\s*\n/)

      rawParagraphs.forEach((raw, paraIdxInScene) => {
        const words = tokenizeParagraph(raw, nextWordIndex)
        if (words.length === 0) return // blank paragraphs (e.g. leading/trailing blank lines) render nothing
        paragraphs.push({
          key: `${chapterIdx}-${sceneIdx}-${paraIdxInScene}`,
          paraIndex: paraIndex++,
          words,
          text: raw,
        })
      })
    })

    return { key: `chapter-${chapterIdx}`, title: chapter.title, paragraphs }
  })
}

/** Renders one paragraph's words as `<span data-w data-c>` word nodes, with plain-text single
 * spaces (real text nodes, not spans) as the only thing separating them. */
function renderParagraphChildren(words: TokenizedWord[]): ReactNode[] {
  const children: ReactNode[] = []
  words.forEach((w, i) => {
    if (i > 0) children.push(' ')
    children.push(
      <span key={w.wordIndex} data-w={w.wordIndex} data-c={w.charOffset}>
        {w.word}
      </span>,
    )
  })
  return children
}

/**
 * Renders a Book's fully-compiled manuscript preview (`useDraftPreview`) as plain, tokenized
 * prose: every word wrapped in a `<span data-w data-c>` (globally sequential word index, plus
 * that word's exact character offset within its own paragraph's raw text), every paragraph in
 * a `<p data-para-index>` (also globally sequential), plus the reading-ruler overlay
 * (`ReadingRuler`, `R` to cycle) and focus mode (`F` to toggle, dims every paragraph but the
 * current one) — both key off one shared `useReadingCursor` call here, so there's only ever
 * one mousemove/keydown listener pair attached regardless of which of the two are active.
 * Read-aloud is a separate later Phase 8 task that keys off the same `data-w`/`data-c`/
 * `data-para-index` attributes; keeping tokenizing itself mechanical keeps that addition
 * purely additive (no re-tokenizing needed).
 *
 * Uses the existing `.manuscript` surface (`index.css`) for all typography/color — left-align
 * is already baked into `.manuscript` and is never overridden here.
 */
export function ManuscriptReader({ bookId }: ManuscriptReaderProps) {
  const { data, isLoading, isError } = useDraftPreview(bookId)
  const containerRef = useRef<HTMLDivElement>(null)
  const { data: settings } = useSettings()
  const updateSettings = useUpdateSettings()
  const readingRulerMode = normalizeReadingRulerMode(settings?.reading_ruler)
  const focusMode = settings?.focus_mode === true
  const { motionOk } = useDelight()

  // Lifted once here so the reading ruler and focus mode share the same mousemove/keydown
  // listener pair instead of each calling `useReadingCursor` (and attaching its own) separately.
  const cursorPosition = useReadingCursor(containerRef)

  const chapters = data ? tokenizeDocument(data.chapters) : []
  const hasContent = chapters.some((chapter) => chapter.paragraphs.length > 0)
  // Flattened in `paraIndex` order (blank paragraphs already excluded by `tokenizeDocument`),
  // so this array's own index — which is exactly what `speak()` reports back via its
  // `onBoundary`/`onParagraphStart` `paraIndex` argument — lines up 1:1 with each paragraph's
  // `data-para-index` below. See the `text` field's doc comment on `TokenizedParagraph`.
  const flatParagraphTexts = chapters.flatMap((chapter) => chapter.paragraphs.map((p) => p.text))

  // `R` cycles off -> grey_bar -> shade -> off (docs/06 Phase 8), persisted via the same
  // settings mutation the Settings screen uses — only registered while there's an actual
  // reading surface with content on screen (see `useReadingShortcut`'s `enabled` param).
  useReadingShortcut(
    'r',
    () => updateSettings.mutate({ reading_ruler: nextReadingRulerMode(readingRulerMode) }),
    hasContent,
  )

  // `F` toggles focus mode on/off, persisted the same way as `R` above.
  useReadingShortcut('f', () => updateSettings.mutate({ focus_mode: !focusMode }), hasContent)

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-1 py-12 text-sm text-muted-foreground">
        <LottiePlayer
          animationData={() => import('../../assets/lottie/loading-loop.json')}
          loop
          ariaHidden
          className="size-16"
        />
        Loading manuscript…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        Couldn&apos;t load the manuscript preview.
      </p>
    )
  }

  if (!hasContent) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        This book doesn&apos;t have any scenes yet — add some on the Canvas to see them here.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <ReadAloudBar paragraphs={flatParagraphTexts} containerRef={containerRef} />
      <div
        ref={containerRef}
        data-reading-surface
        tabIndex={0}
        className="manuscript relative rounded-xl p-6 outline-none"
      >
        {chapters.map((chapter) =>
          chapter.paragraphs.length === 0 ? null : (
            <section key={chapter.key} className="mb-8">
              {chapter.title && <h2 className="mb-3 text-xl font-semibold">{chapter.title}</h2>}
              {chapter.paragraphs.map((para) => {
                // Dim every paragraph except whichever one `cursorPosition` currently points
                // at — once focus mode is on and the reader has moved the mouse/pressed an
                // arrow key at least once. Before that first move, `cursorPosition` is `null`
                // and nothing is dimmed (mirrors the ruler's own "renders nothing until moved"
                // behavior), so the reader never sees the whole page dim with no indication of
                // which paragraph is "current".
                const isDimmed =
                  focusMode &&
                  cursorPosition !== null &&
                  cursorPosition.paraIndex !== para.paraIndex
                const dimStyle: CSSProperties | undefined = isDimmed
                  ? { transition: motionOk ? 'opacity 100ms ease-out' : 'none' }
                  : undefined
                return (
                  <p
                    key={para.key}
                    data-para-index={para.paraIndex}
                    className={cn('mb-4', isDimmed && 'opacity-40')}
                    style={dimStyle}
                  >
                    {renderParagraphChildren(para.words)}
                  </p>
                )
              })}
            </section>
          ),
        )}
        <ReadingRuler position={cursorPosition} mode={readingRulerMode} />
      </div>
    </div>
  )
}

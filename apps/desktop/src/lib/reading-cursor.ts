import { useEffect, useRef, useState, type RefObject } from 'react'

/**
 * Position of the "current" paragraph, expressed relative to the reading container
 * (`data-reading-surface`) so a consumer (reading-ruler overlay, focus mode) can position
 * itself with plain `style={{ top, height }}` inside that same container — no further
 * coordinate math needed on the consumer side.
 */
export interface ReadingCursorPosition {
  top: number
  height: number
  paraIndex: number
}

/** Finds every `[data-para-index]` element currently in the container, in document order. */
function getParagraphs(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>('[data-para-index]'))
}

function paraIndexOf(el: HTMLElement): number {
  const raw = el.getAttribute('data-para-index')
  return raw === null ? 0 : Number(raw)
}

/** One paragraph's measured rect, cached in container-relative coordinates (`getBoundingClientRect()`
 * deltas against the container, same semantic the old per-frame `relativeRect()` used) — so, once
 * built, this stays valid across scroll (container and its children move together in the viewport)
 * without needing to re-measure. Only invalidated by an actual layout change (resize) or the
 * paragraph set itself changing (content mutation) — see `useReadingCursor`. */
interface CachedParagraph {
  paraIndex: number
  top: number
  bottom: number
  height: number
}

/** Measures every `[data-para-index]` element in `container` exactly once and returns their
 * rects sorted ascending by `top` (document order, which is also visual top-to-bottom order for
 * stacked prose paragraphs) — the one-time cost the per-frame mousemove/keydown handlers below
 * are built to avoid paying again. */
function buildParagraphCache(container: HTMLElement): CachedParagraph[] {
  const containerRect = container.getBoundingClientRect()
  const cache = getParagraphs(container).map((el) => {
    const rect = el.getBoundingClientRect()
    return {
      paraIndex: paraIndexOf(el),
      top: rect.top - containerRect.top,
      bottom: rect.bottom - containerRect.top,
      height: rect.height,
    }
  })
  // Sorted defensively — document order already matches visual top-to-bottom order for this
  // reader's plain stacked-paragraph layout, but the binary search below assumes ascending
  // `top`, so guarantee it rather than trust it.
  cache.sort((a, b) => a.top - b.top)
  return cache
}

/** The cached paragraph whose vertical span contains `relativeY`, or — if `relativeY` is above
 * the first / below the last / in a gap between paragraphs — whichever cached paragraph is
 * closest. `cache` must be sorted ascending by `top` (as `buildParagraphCache` guarantees):
 * binary search for the first paragraph whose `bottom >= relativeY`, an O(log n) replacement
 * for the old O(n) linear scan (which also re-measured every element every call). */
function findClosestInCache(
  cache: CachedParagraph[],
  relativeY: number,
): CachedParagraph | null {
  if (cache.length === 0) return null

  let lo = 0
  let hi = cache.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (cache[mid].bottom < relativeY) {
      lo = mid + 1
    } else {
      hi = mid
    }
  }

  const candidate = cache[lo]
  if (relativeY >= candidate.top && relativeY <= candidate.bottom) {
    return candidate
  }

  // `relativeY` falls in the gap before `candidate` (or above everything) — check whether the
  // previous paragraph's bottom edge is actually closer than `candidate`'s top edge.
  if (lo > 0) {
    const prev = cache[lo - 1]
    const distPrev = relativeY - prev.bottom
    const distCandidate = candidate.top - relativeY
    if (distPrev >= 0 && distPrev < distCandidate) {
      return prev
    }
  }

  return candidate
}

/**
 * Tracks which manuscript paragraph the reader's attention is "on" — driven by mouse
 * position (throttled to one measurement per animation frame) and by ArrowUp/ArrowDown
 * when the reading surface has focus. Read-only: this hook never writes to the DOM, it only
 * measures it and hands back `{top, height, paraIndex}` for a consumer overlay to render
 * against. Returns `null` until the reader has moved the mouse over a paragraph or pressed
 * an arrow key at least once.
 */
export function useReadingCursor(
  containerRef: RefObject<HTMLElement | null>,
): ReadingCursorPosition | null {
  const [position, setPosition] = useState<ReadingCursorPosition | null>(null)
  const rafRef = useRef<number | null>(null)
  const pendingClientYRef = useRef<number | null>(null)
  // Mirrors `position` so `handleKeyDown` (subscribed once per container, see the effect's
  // deps below) always reads the latest value rather than the one captured at mount time.
  const positionRef = useRef<ReadingCursorPosition | null>(null)
  positionRef.current = position
  // The one-time-measured paragraph rects (container-relative), rebuilt only on an actual
  // content/layout change — never on every mousemove/keydown. See the ResizeObserver/
  // MutationObserver below for exactly what triggers a rebuild.
  const cacheRef = useRef<CachedParagraph[]>([])

  function updatePosition(next: ReadingCursorPosition) {
    positionRef.current = next
    setPosition(next)
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    function recache() {
      if (!container) return
      cacheRef.current = buildParagraphCache(container)
    }

    recache()

    function flushMouseMove() {
      rafRef.current = null
      const clientY = pendingClientYRef.current
      if (clientY === null || !container) return
      pendingClientYRef.current = null

      const cache = cacheRef.current
      if (cache.length === 0) return

      // The only per-frame rect read is the container's own — one call, not one per paragraph
      // — used solely to convert this mousemove's viewport-space `clientY` into the same
      // container-relative space the cache was built in. Everything else below is array lookup
      // (binary search), no DOM access, so no forced layout on the hot path.
      const containerRect = container.getBoundingClientRect()
      const relativeY = clientY - containerRect.top
      const target = findClosestInCache(cache, relativeY)
      if (!target) return

      updatePosition({ top: target.top, height: target.height, paraIndex: target.paraIndex })
    }

    function handleMouseMove(event: MouseEvent) {
      pendingClientYRef.current = event.clientY
      // Only the latest move per frame is ever processed — any move superseded before the
      // next frame fires is simply overwritten above, never queued.
      if (rafRef.current === null) {
        rafRef.current = requestAnimationFrame(flushMouseMove)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
      if (!container) return

      const isContainerFocused =
        document.activeElement === container || container.contains(event.target as Node)
      if (!isContainerFocused) return

      const cache = cacheRef.current
      if (cache.length === 0) return

      const current = positionRef.current
      const currentIndex = current
        ? cache.findIndex((p) => p.paraIndex === current.paraIndex)
        : -1

      let nextIndex: number
      if (currentIndex === -1) {
        nextIndex = event.key === 'ArrowDown' ? 0 : cache.length - 1
      } else {
        const delta = event.key === 'ArrowDown' ? 1 : -1
        nextIndex = Math.min(Math.max(currentIndex + delta, 0), cache.length - 1)
      }

      const target = cache[nextIndex]
      updatePosition({ top: target.top, height: target.height, paraIndex: target.paraIndex })
      event.preventDefault()
    }

    container.addEventListener('mousemove', handleMouseMove)
    container.addEventListener('keydown', handleKeyDown)

    // Re-measure on an actual layout change to the container itself (e.g. the panel/window
    // being resized reflows paragraph widths/heights). `ResizeObserver` also fires once
    // immediately on `observe()`, so this is a harmless second recache right after the one
    // above, not a bug.
    const resizeObserver = new ResizeObserver(recache)
    resizeObserver.observe(container)

    // Re-measure when the paragraph set itself changes under this same mounted container —
    // e.g. the draft preview refetches (front matter edit, scene edit elsewhere) while this
    // tab/reader stays mounted, without a fresh `ManuscriptReader` mount to naturally reset
    // things. `subtree: true` because paragraphs live under per-chapter `<section>` wrappers,
    // not as the container's direct children.
    const mutationObserver = new MutationObserver(recache)
    mutationObserver.observe(container, { childList: true, subtree: true })

    // Defensive per-instructions: covers layout shifts that change paragraph rects without
    // changing the container's own box (e.g. a font-size/zoom change), which `ResizeObserver`
    // on the container alone might not catch. Scroll is deliberately NOT a trigger here — both
    // the container and its paragraphs move together in the viewport as the page/container
    // scrolls, so the container-relative offsets cached above stay valid.
    function handleWindowResize() {
      recache()
    }
    window.addEventListener('resize', handleWindowResize)

    return () => {
      container.removeEventListener('mousemove', handleMouseMove)
      container.removeEventListener('keydown', handleKeyDown)
      resizeObserver.disconnect()
      mutationObserver.disconnect()
      window.removeEventListener('resize', handleWindowResize)
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      pendingClientYRef.current = null
      cacheRef.current = []
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef])

  return position
}

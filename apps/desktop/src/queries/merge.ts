import { useCallback, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { API_BASE, api } from '@/lib/api'
import type { CanvasNode } from '@/lib/api'

/** Mirrors app/services/llm_orchestrator.py ProviderName — which leg actually served the
 * streamed suggestion (same union `queries/enhance.ts` uses for the same reason). */
export type MergeProvider = 'ollama' | 'groq'

export interface MergeScenesStartInput {
  scene_ids: string[]
  book_id: string
}

interface MergeState {
  streamedText: string
  isStreaming: boolean
  provider: MergeProvider | null
  logId: string | null
  error: string | null
}

const INITIAL_STATE: MergeState = {
  streamedText: '',
  isStreaming: false,
  provider: null,
  logId: null,
  error: null,
}

/** Identical shape to `queries/enhance.ts`'s `EnhanceDeltaFrame` — `POST /llm/merge-scenes`
 * mirrors `/llm/enhance`'s SSE framing EXACTLY (see `app/api/llm.py` `merge_scenes`
 * docstring): bare `delta`/`provider` frames, then one `done` frame, or an `error` frame. */
interface MergeDeltaFrame {
  delta: string
  provider: MergeProvider
}

interface MergeDoneFrame {
  provider: MergeProvider
  log_id: string
}

interface MergeErrorFrame {
  message: string
  log_id: string
}

/** One `\n\n`-delimited SSE frame, split into its `event:`/`data:` lines — identical framing
 * to `queries/enhance.ts`'s `parseFrame` (same backend `_sse()` helper on both endpoints). */
function parseFrame(frame: string): { event: string | null; data: unknown } | null {
  let event: string | null = null
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trim())
    }
  }
  if (dataLines.length === 0) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}

/** Streams one AI-assisted merge suggestion from `POST /llm/merge-scenes` (PHASE11.md
 * Workstream B, "AI-assisted multi-node merge reusing the Enhance seam exactly") — this
 * hook is the merge-feature's exact counterpart to `queries/enhance.ts`'s `useEnhance`,
 * built against the same SSE framing on purpose (see `parseFrame` above). The model is
 * instructed (`prompt_builder._MERGE_TASK_INSTRUCTION`) to emit one plain-text blob shaped
 * like `TITLE: <title>\nDESCRIPTION:\n<description>` — `streamedText` is that raw,
 * still-accumulating blob; `parseMergeSuggestion` below splits it into title/description
 * once the caller wants to render or accept it.
 *
 * READ-ONLY guarantee: like `useEnhance`, this hook only ever accumulates the streamed
 * suggestion into its own local `streamedText` state — it never writes a Scene or canvas
 * link itself. Turning the suggestion into a real merge is the caller's job: render it for
 * review, then call `useAcceptMergeScenes` (below) only once the user explicitly accepts. */
export function useMergeScenesSuggestion() {
  const [state, setState] = useState<MergeState>(INITIAL_STATE)
  const controllerRef = useRef<AbortController | null>(null)

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setState((prev) => ({ ...prev, isStreaming: false }))
  }, [])

  const start = useCallback(async (input: MergeScenesStartInput) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setState({ ...INITIAL_STATE, isStreaming: true })

    const applyFrame = (parsed: { event: string | null; data: unknown }) => {
      if (parsed.event === 'done') {
        const data = parsed.data as MergeDoneFrame
        setState((prev) => ({ ...prev, isStreaming: false, provider: data.provider, logId: data.log_id }))
      } else if (parsed.event === 'error') {
        const data = parsed.data as MergeErrorFrame
        setState((prev) => ({ ...prev, isStreaming: false, error: data.message, logId: data.log_id }))
      } else {
        const data = parsed.data as MergeDeltaFrame
        setState((prev) => ({
          ...prev,
          streamedText: prev.streamedText + data.delta,
          provider: data.provider,
        }))
      }
    }

    try {
      const res = await fetch(`${API_BASE}/llm/merge-scenes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`POST /llm/merge-scenes → ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let boundary = buffer.indexOf('\n\n')
        while (boundary !== -1) {
          const frame = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const parsed = parseFrame(frame)
          if (parsed) applyFrame(parsed)
          boundary = buffer.indexOf('\n\n')
        }
      }
      // Flush a trailing frame in case the stream ended without a final `\n\n`.
      const trailing = parseFrame(buffer)
      if (trailing) applyFrame(trailing)
    } catch (err) {
      if (controller.signal.aborted) return // cancel() already reset isStreaming
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        error: err instanceof Error ? err.message : 'Merge suggestion failed',
      }))
    }
  }, [])

  return { ...state, start, cancel }
}

/** Splits a merge suggestion's raw streamed text into title/description, per the
 * `TITLE: <title>\nDESCRIPTION:\n<description>` shape `prompt_builder._MERGE_TASK_INSTRUCTION`
 * asks the model for. Tolerant of a still-streaming (partial/mid-token) blob — a caller
 * driving a live preview while `isStreaming` is true will see `description` grow frame by
 * frame, and `title` fill in once the model has emitted the `DESCRIPTION:` marker. */
export function parseMergeSuggestion(streamedText: string): { title: string; description: string } {
  const marker = streamedText.indexOf('DESCRIPTION:')
  if (marker === -1) {
    return { title: streamedText.replace(/^TITLE:\s*/, '').trim(), description: '' }
  }
  const titlePart = streamedText.slice(0, marker).replace(/^TITLE:\s*/, '').trim()
  const descriptionPart = streamedText.slice(marker + 'DESCRIPTION:'.length).trim()
  return { title: titlePart, description: descriptionPart }
}

/** Convenience wrapper around `parseMergeSuggestion` for callers that just want the live
 * split without re-deriving it themselves (e.g. the merge-review dialog, PHASE11.md task
 * 11's separate follow-up). */
export function useMergeSuggestionParts(streamedText: string) {
  return useMemo(() => parseMergeSuggestion(streamedText), [streamedText])
}

export interface AcceptMergeScenesInput {
  source_scene_ids: string[]
  merged_title: string
  merged_description: string
}

/** Writes the merge the user just reviewed from `useMergeScenesSuggestion`'s SSE suggestion
 * into the canvas — `POST /llm/merge-scenes/accept` (PHASE11.md Workstream B task 11). Plain
 * synchronous `useMutation`, same shape as `queries/canvas.ts`'s other canvas-writing
 * mutations (`useCreateEdge`/`useDeleteEdge` etc.) — invalidates the `['canvas', bookId]`
 * query on success so both the new merged node AND the now-archived source nodes' removal
 * show up together from one consistent refetch (a partial cache patch would show the new
 * node appearing before the sources visibly disappear). */
export function useAcceptMergeScenes(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: AcceptMergeScenesInput) => {
      if (!bookId) throw new Error('No book id')
      return api.post<{ node: CanvasNode }>('/llm/merge-scenes/accept', { book_id: bookId, ...input })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not merge the selected nodes'),
  })
}

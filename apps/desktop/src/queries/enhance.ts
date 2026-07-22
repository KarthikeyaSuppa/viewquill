import { useCallback, useRef, useState } from 'react'
import { API_BASE, api } from '@/lib/api'

/** Mirrors app/models/schemas.py EnhanceMode (docs/04-LLM-INTEGRATION.md, docs/06 Phase 2
 * tasks D1/H1). */
export type EnhanceMode = 'grammar' | 'prose' | 'continuity'

/** Mirrors app/services/llm_orchestrator.py ProviderName — which leg actually served the
 * streamed suggestion, shown to the user via the provider Badge in <EnhanceDiff/>. */
export type EnhanceProvider = 'ollama' | 'groq'

export interface EnhanceStartInput {
  mode: EnhanceMode
  text: string
  scene_id?: string
  book_id?: string
  field?: string
  entity_type?: string
  entity_id?: string
}

interface EnhanceState {
  streamedText: string
  isStreaming: boolean
  provider: EnhanceProvider | null
  logId: string | null
  error: string | null
}

const INITIAL_STATE: EnhanceState = {
  streamedText: '',
  isStreaming: false,
  provider: null,
  logId: null,
  error: null,
}

interface EnhanceDeltaFrame {
  delta: string
  provider: EnhanceProvider
}

interface EnhanceDoneFrame {
  provider: EnhanceProvider
  log_id: string
}

interface EnhanceErrorFrame {
  message: string
  log_id: string
}

/** One `\n\n`-delimited SSE frame, split into its `event:`/`data:` lines per
 * app/api/llm.py `_sse()`. Bare `data:`-only frames (progress deltas) have `event ===
 * null`; the backend also sends `event: done` and `event: error` frames. */
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

/** Streams one Enhance/continuity suggestion from `POST /llm/enhance` (docs/04, docs/06
 * Phase 2 tasks D1/H1).
 *
 * READ-ONLY guarantee: this hook only ever accumulates the streamed suggestion text into
 * its own local `streamedText` state — it has NO code path that writes to a Scene or
 * screenplay element. Turning the suggestion into a real edit is entirely the caller's
 * job: render `streamedText` inside `<EnhanceDiff/>` and have the caller's own Accept
 * handler issue the actual `useUpdateScene`/`useUpdateElement` PATCH. Reject (or just
 * closing the review panel) never calls anything here that mutates data. */
export function useEnhance() {
  const [state, setState] = useState<EnhanceState>(INITIAL_STATE)
  const controllerRef = useRef<AbortController | null>(null)

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    controllerRef.current = null
    setState((prev) => ({ ...prev, isStreaming: false }))
  }, [])

  const start = useCallback(async (input: EnhanceStartInput) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setState({ ...INITIAL_STATE, isStreaming: true })

    const applyFrame = (parsed: { event: string | null; data: unknown }) => {
      if (parsed.event === 'done') {
        const data = parsed.data as EnhanceDoneFrame
        setState((prev) => ({ ...prev, isStreaming: false, provider: data.provider, logId: data.log_id }))
      } else if (parsed.event === 'error') {
        const data = parsed.data as EnhanceErrorFrame
        setState((prev) => ({ ...prev, isStreaming: false, error: data.message, logId: data.log_id }))
      } else {
        const data = parsed.data as EnhanceDeltaFrame
        setState((prev) => ({
          ...prev,
          streamedText: prev.streamedText + data.delta,
          provider: data.provider,
        }))
      }
    }

    try {
      const res = await fetch(`${API_BASE}/llm/enhance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`POST /llm/enhance → ${res.status}`)
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
        error: err instanceof Error ? err.message : 'Enhance failed',
      }))
    }
  }, [])

  return { ...state, start, cancel }
}

/** Records the user's Accept/Reject decision against the audit-log row `/llm/enhance`
 * already wrote (docs/06 Phase 2 task D1) — mirrors app/api/llm.py `accept_log`. This
 * call ONLY ever flips that one log row's `accepted` flag; it never touches a Scene or
 * screenplay element. The actual text write (on Accept) is a separate, explicit PATCH
 * the caller issues itself via `useUpdateScene`/`useUpdateElement`. */
export function acceptLog(logId: string, accepted: boolean) {
  return api.post(`/llm/log/${logId}/accept`, { accepted })
}

import { getNote, putNote } from '@/queries/notes'
import type { SyncAdapter, SyncStatus } from '@/lib/sync/adapter'

const POLL_INTERVAL_MS = 1500
const PUBLISH_DEBOUNCE_MS = 500
const UPDATED_BY = 'desktop-local'

/**
 * LAN `SyncAdapter` (T3+T4): polls `GET /notes/{channel}` on `POLL_INTERVAL_MS` and
 * debounces `PUT /notes/{channel}` on publish by `PUBLISH_DEBOUNCE_MS`. Last-write-wins —
 * every publish sends `Date.now()` as `updated_at` (the fixed backend contract), and
 * `subscribe` only fires `onRemote` when the server's `updated_at` is strictly newer than
 * the last value this adapter has seen (from either a poll or its own most recent
 * successful publish), so a save never echoes back to itself as a "remote" update.
 *
 * Errors (network failure or a non-2xx response, both surfaced by `lib/api.ts` throwing)
 * are swallowed here and turned into a `'offline'`/`'error'` status rather than thrown —
 * a background poll/debounced write failing must never crash the editor mid-typing.
 */
export function createLanAdapter(channel: string): SyncAdapter {
  let lastSeenUpdatedAt = 0
  let status: SyncStatus = 'idle'
  const statusListeners = new Set<(status: SyncStatus) => void>()
  let publishTimer: ReturnType<typeof setTimeout> | null = null
  let pendingContent: string | null = null

  function setStatus(next: SyncStatus) {
    if (status === next) return
    status = next
    for (const listener of statusListeners) listener(next)
  }

  async function flushPublish() {
    if (pendingContent === null) return
    const content = pendingContent
    pendingContent = null
    setStatus('syncing')
    try {
      const note = await putNote(channel, { content, updated_at: Date.now(), updated_by: UPDATED_BY })
      lastSeenUpdatedAt = note.updated_at
      setStatus('idle')
    } catch {
      setStatus('offline')
    }
  }

  return {
    subscribe(onRemote) {
      let cancelled = false

      async function poll() {
        try {
          const note = await getNote(channel)
          if (cancelled) return
          if (note.updated_at > lastSeenUpdatedAt) {
            lastSeenUpdatedAt = note.updated_at
            onRemote({ content: note.content, updated_at: note.updated_at })
          }
          // A successful poll clears a stale offline/error status, but never stomps
          // 'syncing' — a publish in flight owns the indicator until it settles.
          if (status === 'offline' || status === 'error') setStatus('idle')
        } catch {
          if (!cancelled) setStatus('offline')
        }
      }

      // Fire once immediately so the editor doesn't sit blank/stale until the first tick,
      // then keep polling on the interval.
      void poll()
      const interval = setInterval(() => void poll(), POLL_INTERVAL_MS)

      return () => {
        cancelled = true
        clearInterval(interval)
        if (publishTimer) {
          clearTimeout(publishTimer)
          publishTimer = null
        }
      }
    },
    publish(content) {
      pendingContent = content
      if (publishTimer) clearTimeout(publishTimer)
      publishTimer = setTimeout(() => {
        publishTimer = null
        void flushPublish()
      }, PUBLISH_DEBOUNCE_MS)
    },
    getStatus() {
      return status
    },
    onStatusChange(listener) {
      statusListeners.add(listener)
      return () => statusListeners.delete(listener)
    },
  }
}

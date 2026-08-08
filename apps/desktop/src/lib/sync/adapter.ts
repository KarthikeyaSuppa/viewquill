/**
 * Sync seam for the Notes tab scratchpad (T3+T4). `lan-adapter.ts` implements this over
 * REST polling against the sidecar's `/notes/{channel}` contract; a later task's Cloud
 * adapter (Firebase-backed, per the plan — not built here, no `firebase` import anywhere
 * in this task) will implement the same interface. `note-editor.tsx` binds to whichever
 * adapter it's given and never needs to know which transport is underneath.
 */

/** A note as received from the remote side — just enough for last-write-wins comparison
 * and rendering; `updated_by`/`rev` from the full `NoteResponse` aren't needed here. */
export interface RemoteNote {
  content: string
  updated_at: number
}

/** Coarse connectivity/sync state for the small indicator in `note-editor.tsx`:
 * `idle` = nothing pending and the last write/read succeeded ("Saved"), `syncing` = a
 * publish is in flight, `offline` = the last request failed to reach the sidecar,
 * `error` = the sidecar responded but rejected the request. Kept as a flat union rather
 * than a richer object — this is a personal scratchpad indicator, not a full sync log. */
export type SyncStatus = 'idle' | 'syncing' | 'offline' | 'error'

export interface SyncAdapter {
  /** Subscribes to remote changes; fires `onRemote` whenever a note newer than the last
   * one this adapter has seen arrives (from a poll, or a push notification for adapters
   * that have one). Returns an unsubscribe function that must stop any timers/sockets it
   * opened — callers (React effects) rely on this for cleanup. */
  subscribe(onRemote: (note: RemoteNote) => void): () => void
  /** Publishes a local edit. Implementations may debounce internally rather than writing
   * on every call — callers should feel free to call this on every keystroke. */
  publish(content: string): void
  /** Synchronous read of the current status, for an initial render before the first
   * `onStatusChange` callback fires. */
  getStatus(): SyncStatus
  /** Subscribes to status transitions. Returns an unsubscribe function. */
  onStatusChange(listener: (status: SyncStatus) => void): () => void
}

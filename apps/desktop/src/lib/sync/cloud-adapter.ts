import { getDocRef, getFirestoreDb, setDocMerged, watchDocSnapshot } from '@/lib/firebase'
import type { RemoteNote, SyncAdapter, SyncStatus } from '@/lib/sync/adapter'

/**
 * NETWORK WALL: this file does NOT import `firebase`/`firebase/*` — it goes through
 * `getFirestoreDb`/`getDocRef`/`setDocMerged`/`watchDocSnapshot`, the thin Firestore
 * pass-throughs `src/lib/firebase.ts` exports for exactly this purpose. `firebase.ts` owns
 * *initialization* (API keys/project config, auth state); this file owns the *data shape*
 * of the one synced document (`notes/{uid}`, its field names, the debounce/LWW policy),
 * which is Notes-tab-specific and doesn't belong in the generic bootstrap module. If you're
 * tempted to add a `firebase` import here, add a wrapper to `firebase.ts` instead — a
 * reviewer greps the repo for `from 'firebase` and expects exactly one hit (that file).
 *
 * Cloud `SyncAdapter` (T7+T8): implements the exact same interface as `lan-adapter.ts`
 * over one Firestore document per signed-in user, `notes/{uid}`. Last-write-wins on the
 * document's `updatedAt` field (epoch ms, same unit as the LAN adapter's `updated_at` —
 * mapped 1:1 here), with the same echo-suppression idea: a publish's own `updatedAt` is
 * recorded as "already seen" *before* the write goes out, so the optimistic local-cache
 * snapshot Firestore fires immediately for our own write is never mistaken for an
 * incoming remote change.
 */

const PUBLISH_DEBOUNCE_MS = 500
const NOTES_COLLECTION = 'notes'

// One id per app session (not per adapter instance — a page reload gets a new one, which
// is fine; this is only ever used for a human-readable "last edited by" hint, never for
// identity/security). `crypto.randomUUID` is available in every target runtime (WebView2 +
// Tauri); the `Math.random` fallback only matters for an unusual embedding that lacks it.
const SESSION_ID =
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10)

interface CloudNoteDoc {
  content: string
  updatedAt: number
  updatedBy: string
  schemaVersion: number
  // Index signature so this shape is also assignable to `setDocMerged`'s
  // `Record<string, unknown>` parameter (it's a `firebase.ts` wrapper, kept generic there
  // rather than importing this Notes-specific type into the network wall).
  [key: string]: unknown
}

/**
 * Creates a `SyncAdapter` bound to `notes/{uid}` for the given signed-in Firebase uid.
 * Callers (`cloud-auth-panel.tsx`) must only construct this after a successful sign-in —
 * `uid` is not re-validated here, and Firestore's own security rules
 * (`firebase/firestore.rules`: `request.auth.uid == uid`) are the real enforcement point.
 */
export function createCloudAdapter(uid: string): SyncAdapter {
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

    const db = getFirestoreDb()
    const ref = getDocRef(db, NOTES_COLLECTION, uid)
    const updatedAt = Date.now()
    // Recorded before the write resolves — see the echo-suppression note above.
    lastSeenUpdatedAt = updatedAt

    setStatus('syncing')
    try {
      const payload: CloudNoteDoc = {
        content,
        updatedAt,
        updatedBy: `desktop-${SESSION_ID}`,
        schemaVersion: 1,
      }
      await setDocMerged(ref, payload)
      setStatus('idle')
    } catch {
      setStatus('offline')
    }
  }

  return {
    subscribe(onRemote) {
      const db = getFirestoreDb()
      const ref = getDocRef(db, NOTES_COLLECTION, uid)

      const unsubscribe = watchDocSnapshot(
        ref,
        (snapshot) => {
          const data = snapshot.data() as CloudNoteDoc | undefined
          if (data && typeof data.updatedAt === 'number' && data.updatedAt > lastSeenUpdatedAt) {
            lastSeenUpdatedAt = data.updatedAt
            if (typeof data.content === 'string') {
              const note: RemoteNote = { content: data.content, updated_at: data.updatedAt }
              onRemote(note)
            }
          }

          // `fromCache` means this snapshot came from the local persistent cache rather
          // than a live server response — either we're offline, or (briefly) the
          // optimistic echo of our own pending write. Don't let that echo stomp a
          // `'syncing'` status that a publish already set; otherwise, treat it as offline.
          if (snapshot.metadata.fromCache) {
            if (status !== 'syncing') setStatus('offline')
          } else if (status === 'offline' || status === 'error') {
            setStatus('idle')
          }
        },
        () => setStatus('error'),
      )

      return () => {
        unsubscribe()
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

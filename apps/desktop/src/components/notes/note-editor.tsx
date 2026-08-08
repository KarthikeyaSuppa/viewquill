import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Textarea } from '@/components/ui/textarea'
import type { SyncAdapter, SyncStatus } from '@/lib/sync/adapter'
import { cn } from '@/lib/utils'

const STATUS_LABEL: Record<SyncStatus, string> = {
  idle: 'Saved',
  syncing: 'Syncing…',
  offline: 'Offline — will retry',
  error: 'Sync error',
}

interface NoteEditorProps {
  /** Sync channel, e.g. `'lan'` or `'cloud'` — used only for the field's id/label, not for
   * picking the adapter (that's `adapterFactory` below). */
  channel: string
  /** Builds the `SyncAdapter` this editor binds to. A factory rather than a ready instance
   * so each mount gets its own adapter (mirrors the old internal `createLanAdapter` call) —
   * important for the Cloud pane, where a new instance must be created per signed-in uid
   * rather than reused across sign-out/sign-in. Both `createLanAdapter` (LAN) and
   * `createCloudAdapter` (Cloud, T7+T8) implement the same `SyncAdapter` interface, so this
   * component never needs to know which transport is underneath. */
  adapterFactory: () => SyncAdapter
  /** Optional head start for the initial render, e.g. `lan-adapter`'s already-cached
   * React Query value (`useLanNote()`, moved up to the call site — see `notes-screen.tsx`)
   * — filled in before `adapter.subscribe`'s first callback lands. The Cloud pane omits
   * this; Firestore's persistent local cache makes `subscribe`'s first snapshot fast
   * enough on its own that a separate head-start query isn't needed there. */
  initialContent?: string
  className?: string
}

/**
 * Auto-growing scratchpad textarea bound to a `SyncAdapter` (T3+T4, generalized in T7+T8
 * to accept any adapter — LAN or Cloud — via `adapterFactory`). Local edits are pushed on
 * every keystroke via `adapter.publish` — the adapter debounces the actual network write
 * itself (~500ms in both `lan-adapter.ts` and `cloud-adapter.ts`), so this component
 * doesn't need its own debounce timer on top of that.
 *
 * Remote-clobber guard: if a remote update arrives while this textarea has focus (the user
 * is actively typing), it's stashed instead of overwriting the live value, and applied on
 * blur. This is a simple last-write-wins heuristic tuned for a personal single-user
 * scratchpad, not real conflict resolution — good enough here, but not a pattern to reuse
 * for anything with concurrent multi-user editing.
 */
export function NoteEditor({ channel, adapterFactory, initialContent, className }: NoteEditorProps) {
  const [value, setValue] = useState('')
  const [status, setStatus] = useState<SyncStatus>('idle')

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isFocusedRef = useRef(false)
  const stashedRemoteRef = useRef<string | null>(null)
  const hasReceivedRemoteRef = useRef(false)
  const adapterRef = useRef<SyncAdapter | null>(null)
  if (!adapterRef.current) {
    adapterRef.current = adapterFactory()
  }

  // Seed from the caller-supplied initial value once — only if a live update from
  // `subscribe` below hasn't already landed and the user hasn't started typing into an
  // empty box yet. The adapter also fetches/subscribes immediately, so this is just a head
  // start using whatever the caller already had cached, not the sole source of the initial
  // value.
  useEffect(() => {
    if (hasReceivedRemoteRef.current || isFocusedRef.current) return
    if (initialContent !== undefined && value === '') {
      setValue(initialContent)
    }
  }, [initialContent, value])

  useEffect(() => {
    const adapter = adapterRef.current
    if (!adapter) return

    const unsubscribeStatus = adapter.onStatusChange(setStatus)
    const unsubscribeRemote = adapter.subscribe((note) => {
      hasReceivedRemoteRef.current = true
      if (isFocusedRef.current) {
        stashedRemoteRef.current = note.content
        return
      }
      setValue(note.content)
    })

    return () => {
      unsubscribeStatus()
      unsubscribeRemote()
    }
    // Intentionally mount-only: the adapter instance is stable for this component's
    // lifetime (created once above), and re-subscribing on every render would open a new
    // interval/listener each time.
  }, [])

  // Auto-grow height — mirrors `components/canvas/node-editor.tsx`'s Description field.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  function handleChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const next = event.target.value
    setValue(next)
    adapterRef.current?.publish(next)
  }

  function handleFocus() {
    isFocusedRef.current = true
  }

  function handleBlur() {
    isFocusedRef.current = false
    if (stashedRemoteRef.current !== null) {
      setValue(stashedRemoteRef.current)
      stashedRemoteRef.current = null
    }
  }

  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={`note-editor-${channel}`} className="sr-only">
        {channel === 'lan' ? 'LAN note' : `${channel} note`}
      </label>
      <Textarea
        id={`note-editor-${channel}`}
        ref={textareaRef}
        value={value}
        onChange={handleChange}
        onFocus={handleFocus}
        onBlur={handleBlur}
        placeholder="Jot something down…"
        className="min-h-32 resize-none overflow-hidden"
      />
      <p aria-live="polite" className="text-xs text-muted-foreground">
        {STATUS_LABEL[status]}
      </p>
    </div>
  )
}

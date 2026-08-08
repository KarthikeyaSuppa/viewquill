import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { NoteEditor } from '@/components/notes/note-editor'
import { CloudAuthPanel } from '@/components/notes/cloud-auth-panel'
import { LanPairingDialog } from '@/components/notes/lan-pairing-dialog'
import { createLanAdapter } from '@/lib/sync/lan-adapter'
import { useLanNote } from '@/queries/notes'

/**
 * Notes tab (T3+T4 LAN, T7+T8 Cloud, T6 LAN pairing): a scratchpad that syncs across
 * devices. Two panes side-by-side on wide viewports, stacked on narrow ones — LAN
 * (`NoteEditor` + `lan-adapter.ts` + `LanPairingDialog` for phone pairing) and Cloud
 * (`CloudAuthPanel` + `cloud-adapter.ts`, Firebase-backed and entirely opt-in — see
 * `src/lib/firebase.ts`'s network-wall comment). Everything else in this route stays
 * local; the LAN pane never touches the network wall at all.
 */
export function NotesScreen() {
  // Lifted up from `NoteEditor` itself (T7+T8 generalized it to take any adapter via
  // `adapterFactory`) so the LAN-specific "head start from cache" behavior stays scoped to
  // the LAN pane's call site instead of living inside the now-adapter-agnostic component.
  const { data: lanNote } = useLanNote()
  const [lanPairingOpen, setLanPairingOpen] = useState(false)

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Notes</h1>
        <p className="text-sm text-muted-foreground">
          A scratchpad that syncs to your other devices.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="glass glass-edge flex flex-col gap-3 rounded-2xl p-5">
          <div>
            <h2 className="text-base font-medium">On your Wi-Fi</h2>
            <p className="text-xs text-muted-foreground">Syncs with devices on the same network.</p>
          </div>

          <NoteEditor channel="lan" adapterFactory={() => createLanAdapter('lan')} initialContent={lanNote?.content} />

          <Button
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => setLanPairingOpen(true)}
          >
            Set up device sync
          </Button>
          <LanPairingDialog open={lanPairingOpen} onOpenChange={setLanPairingOpen} />
        </section>

        <section className="glass glass-edge flex flex-col gap-3 rounded-2xl p-5">
          <div>
            <h2 className="text-base font-medium">Anywhere (cloud)</h2>
            <p className="text-xs text-muted-foreground">Sign in once to sync this note anywhere.</p>
          </div>

          <CloudAuthPanel />
        </section>
      </div>
    </div>
  )
}

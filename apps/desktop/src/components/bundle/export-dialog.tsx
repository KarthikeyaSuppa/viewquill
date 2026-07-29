import { type FormEvent, useEffect, useState } from 'react'
import { TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useExportBundle } from '@/queries/bundle'

const MIN_PASSPHRASE_LENGTH = 8

/**
 * "Export backup" dialog (docs/06 Phase 7, final task) — encrypts the whole Book (scenes,
 * codex, outline, images, continuity flags — everything `.quillproj` covers) with a
 * passphrase the user chooses and downloads it. There's no server-side passphrase
 * recovery (that's the whole point of client-side encryption for a local-first app), so
 * this is the one export flow that warns explicitly before it lets the user proceed.
 */
export function ExportBundleDialog({
  bookId,
  open,
  onOpenChange,
}: {
  bookId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const exportBundle = useExportBundle(bookId)
  const [passphrase, setPassphrase] = useState('')
  const [confirmPassphrase, setConfirmPassphrase] = useState('')

  // Reset the form every time the dialog re-opens — a passphrase left in memory across
  // opens is unnecessary exposure for no benefit.
  useEffect(() => {
    if (open) {
      setPassphrase('')
      setConfirmPassphrase('')
    }
  }, [open])

  const tooShort = passphrase.length > 0 && passphrase.length < MIN_PASSPHRASE_LENGTH
  const mismatch = confirmPassphrase.length > 0 && passphrase !== confirmPassphrase
  const canSubmit = passphrase.length >= MIN_PASSPHRASE_LENGTH && passphrase === confirmPassphrase

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!canSubmit) return
    exportBundle.mutate(passphrase, {
      onSuccess: () => onOpenChange(false),
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Export encrypted backup</DialogTitle>
          <DialogDescription>
            Downloads this Book — scenes, Codex, outline, images and all — as one encrypted
            <code className="mx-1 rounded bg-muted px-1 py-0.5 text-xs">.quillproj</code>
            file you can restore later or move to another computer.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <p>
            You&apos;ll need this passphrase to restore the backup — there is no way to
            recover it if you forget it. Write it down somewhere safe.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bundle-export-passphrase">Passphrase</Label>
            <Input
              id="bundle-export-passphrase"
              type="password"
              autoFocus
              autoComplete="new-password"
              value={passphrase}
              onChange={(event) => setPassphrase(event.target.value)}
              aria-invalid={tooShort}
            />
            {tooShort && (
              <p className="text-xs text-destructive">
                Must be at least {MIN_PASSPHRASE_LENGTH} characters.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="bundle-export-passphrase-confirm">Confirm passphrase</Label>
            <Input
              id="bundle-export-passphrase-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmPassphrase}
              onChange={(event) => setConfirmPassphrase(event.target.value)}
              aria-invalid={mismatch}
            />
            {mismatch && <p className="text-xs text-destructive">Passphrases don&apos;t match.</p>}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || exportBundle.isPending}>
              {exportBundle.isPending ? 'Exporting…' : 'Export encrypted backup'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

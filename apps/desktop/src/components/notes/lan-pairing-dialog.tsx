import { WifiOff, ShieldAlert } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import {
  useLanShareDetails,
  useLanShareStatus,
  useStartLanShare,
  useStopLanShare,
} from '@/queries/notes'

/**
 * Notes tab (T6): the LAN pane's "Set up device sync" dialog — starts/stops the sidecar's
 * tiny local HTTP server that a phone on the same Wi-Fi can hit directly to read/write the
 * `lan` channel note, and renders the QR code + 6-digit fallback code the phone needs to
 * pair. Sharing is a server-side toggle, not tied to this dialog's lifecycle — closing the
 * dialog (or the whole Notes tab) does *not* stop sharing; only the explicit "Stop sharing"
 * button does. Polling (`useLanShareStatus(open)`) is what lets the dialog reflect reality
 * if sharing was stopped some other way while the dialog is open.
 */
export function LanPairingDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: status, isPending: statusPending } = useLanShareStatus(open)
  // Only the `start` response carries the pairing code/QR payload — `status` never does
  // (see the fixed contract) — so this reads the last-known pair from a small cache slot
  // that survives the dialog's own close/reopen. See `queries/notes.ts`.
  const { data: details } = useLanShareDetails()
  const startShare = useStartLanShare()
  const stopShare = useStopLanShare()

  const sharing = status?.sharing ?? false

  const startErrorDetail =
    startShare.error instanceof ApiError
      ? startShare.error.detail ?? "That port is busy — try again."
      : startShare.error
        ? "That port is busy — try again."
        : null

  function handleStart() {
    startShare.reset()
    startShare.mutate()
  }

  function handleStop() {
    stopShare.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Set up device sync</DialogTitle>
          <DialogDescription>
            Pair a phone on your Wi-Fi so it can read and write this same note.
          </DialogDescription>
        </DialogHeader>

        {!sharing && (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">
              Starting device sync opens a small local server on this computer so a phone on
              the same Wi-Fi network can connect directly to it — nothing goes over the
              internet.
            </p>

            {details && !statusPending && (
              <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
                <WifiOff className="mt-0.5 size-4 shrink-0" />
                Sync was stopped, so the previous QR code and pairing code no longer work.
                Start again to get a new one.
              </p>
            )}

            {startErrorDetail && (
              <p role="alert" className="text-sm text-destructive">
                {startErrorDetail}
              </p>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="button" onClick={handleStart} disabled={startShare.isPending}>
                {startShare.isPending ? 'Starting…' : 'Start sharing'}
              </Button>
            </DialogFooter>
          </div>
        )}

        {sharing && (
          <div className="flex flex-col gap-4">
            {details ? (
              <>
                <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-muted/30 p-4">
                  <div
                    className="rounded-lg bg-white p-2"
                    role="img"
                    aria-label="QR code — scan with the Quillnight phone app to pair this device"
                  >
                    <QRCodeSVG value={JSON.stringify(details.qr_payload)} size={176} />
                  </div>

                  <div className="flex flex-col items-center gap-1">
                    <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                      Pairing code
                    </span>
                    <span
                      aria-label={`Pairing code: ${details.pairing_code.split('').join(' ')}`}
                      className="font-mono text-3xl font-bold tracking-[0.35em] tabular-nums"
                    >
                      {details.pairing_code}
                    </span>
                  </div>
                </div>

                {status && status.host_ips.length > 0 && (
                  <div className="flex flex-col gap-1 text-center text-sm text-muted-foreground">
                    <span>Or enter this address manually:</span>
                    {status.host_ips.map((ip) => (
                      <span key={ip} className="font-mono text-foreground">
                        {ip}:{status.lan_port}
                      </span>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                Device sync is already running, but this window no longer has the pairing
                code (it doesn&apos;t survive an app restart). Stop and start again to get a
                fresh code.
              </p>
            )}

            <Separator />

            <div className="flex flex-col gap-1.5 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">On your phone:</p>
              <ol className="list-decimal space-y-1 pl-4">
                <li>Open the Quillnight app.</li>
                <li>Scan this QR code, or type the 6-digit pairing code.</li>
                <li>Make sure both devices are on the same Wi-Fi network.</li>
              </ol>
              <p className="pt-1">
                Windows may show a one-time firewall prompt the first time you share — allow
                it so your phone can connect.
              </p>
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="destructive"
                onClick={handleStop}
                disabled={stopShare.isPending}
              >
                {stopShare.isPending ? 'Stopping…' : 'Stop sharing'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

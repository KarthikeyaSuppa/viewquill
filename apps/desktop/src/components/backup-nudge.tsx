import { useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { CloudUpload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useBackupStatus, useRunBackup } from '@/queries/backups'

const STALE_MS = 24 * 60 * 60 * 1000

function isStale(lastBackupAt: string | null): boolean {
  if (!lastBackupAt) return true
  return Date.now() - new Date(lastBackupAt).getTime() > STALE_MS
}

/**
 * Backup-nudge banner (docs/06 Phase 9 task 3, docs/14-DEFERRED-ENHANCEMENTS.md §B2).
 * Shows when the local DB has never been backed up, or the last backup is more than 24h
 * old, with a one-click "Back up now" that hits `POST /backups/run` and refetches
 * `useBackupStatus` so the banner clears itself immediately on success.
 *
 * Not mounted anywhere yet — see the Phase 9 report for the suggested mount point
 * (`src/components/app-shell.tsx`, inside `<main>` above `<Outlet />`).
 *
 * Dismissal is session-only (component state, not persisted) — reappears next launch or
 * next time it goes stale again, same spirit as `src/components/onboarding/reading-comfort-wizard.tsx`
 * not needing a "never show again" beyond the one onboarding flag.
 */
export function BackupNudge() {
  const [dismissed, setDismissed] = useState(false)
  const reduceMotion = useReducedMotion()
  const { data: status } = useBackupStatus()
  const runBackup = useRunBackup()

  const stale = status ? isStale(status.last_backup_at) : false
  const visible = stale && !dismissed

  return (
    <AnimatePresence initial={false}>
      {visible && (
        <motion.div
          role="status"
          initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -8 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
          className="glass glass-edge mb-4 flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3"
        >
          <CloudUpload className="size-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="min-w-0 flex-1 text-sm text-foreground/90">
            {status?.last_backup_at
              ? "Your local backup hasn't run in a while. Back up now to keep your work safe."
              : "You haven't backed up your library yet. Back up now to keep your work safe."}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => runBackup.mutate()}
            disabled={runBackup.isPending}
            className="shrink-0 gap-1.5"
          >
            <CloudUpload className="size-3.5" />
            {runBackup.isPending ? 'Backing up…' : 'Back up now'}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Dismiss backup reminder"
            className="shrink-0"
            onClick={() => setDismissed(true)}
          >
            <X className="size-3.5" />
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Local DB backup status + manual trigger (docs/06 Phase 9 task 3, backup-nudge banner).
 * `GET /backups/status` / `POST /backups/run` aren't in the generated `packages/api-types/
 * schema.d.ts` yet (would need `npm run gen:types` against a running sidecar) — this
 * mirrors `src/queries/bundle.ts`'s precedent of hand-declaring the shape locally rather
 * than blocking on regeneration. Matches `app/services/backup_service.py::backup_status`.
 */

export interface BackupStatus {
  last_backup_at: string | null
  next_backup_at: string | null
}

const BACKUP_STATUS_KEY = ['backups', 'status']

/** Polls `/backups/status` (docs/06 Phase 9 task 2) so the nudge banner reflects staleness
 * without requiring a manual refresh — also refetches on window focus, same as other
 * long-lived background queries in this app (see `src/queries/health.ts`). */
export function useBackupStatus() {
  return useQuery({
    queryKey: BACKUP_STATUS_KEY,
    queryFn: () => api.get<BackupStatus>('/backups/status'),
    refetchInterval: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  })
}

/** Triggers an immediate manual backup rotation (`POST /backups/run`), then refetches the
 * status query so the nudge banner clears/updates without waiting for the next poll. */
export function useRunBackup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ path: string }>('/backups/run'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: BACKUP_STATUS_KEY })
    },
  })
}

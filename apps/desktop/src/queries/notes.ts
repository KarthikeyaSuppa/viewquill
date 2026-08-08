import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  api,
  type LanShareStartResult,
  type LanShareStatus,
  type LanShareStopResult,
  type NoteResponse,
  type NoteUpdateInput,
} from '@/lib/api'

/**
 * Notes tab (T3+T4): plain fetchers + TanStack hooks for the `/notes/{channel}` contract.
 *
 * `getNote`/`putNote` are exported as plain promise-returning functions (not just hooks) so
 * `src/lib/sync/lan-adapter.ts` can share the exact same request shape for its poll/publish
 * loop, which runs outside of React Query's cache/component lifecycle — the hooks below wrap
 * them for the editor/status UI, per the task's "share it" note.
 */

const LAN_CHANNEL = 'lan'

export function getNote(channel: string) {
  return api.get<NoteResponse>(`/notes/${channel}`)
}

export function putNote(channel: string, body: NoteUpdateInput) {
  return api.put<NoteResponse>(`/notes/${channel}`, body)
}

/** Reads the LAN-channel scratchpad note. */
export function useLanNote() {
  return useQuery({
    queryKey: ['notes', LAN_CHANNEL],
    queryFn: () => getNote(LAN_CHANNEL),
  })
}

/** Publishes a new LAN note body; last-write-wins via `updated_at` (epoch ms, set to
 * `Date.now()` at call time per the fixed backend contract). */
export function useSetLanNote() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (content: string) =>
      putNote(LAN_CHANNEL, { content, updated_at: Date.now(), updated_by: 'desktop-local' }),
    onSuccess: (note) => {
      queryClient.setQueryData(['notes', LAN_CHANNEL], note)
    },
    onError: () => toast.error('Could not sync your note'),
  })
}

// ── LAN device pairing (T6): the sidecar's tiny local HTTP server a phone on the same
// Wi-Fi can hit directly to read/write the `lan` channel note. Endpoints are fixed at
// `/notes/lan/share/*` (not parameterized by channel — this is a LAN-only feature, there's
// no cloud equivalent), see `src/components/notes/lan-pairing-dialog.tsx`. ──

const LAN_SHARE_STATUS_KEY = ['notes', LAN_CHANNEL, 'share-status']
// `GET .../share/status` deliberately omits `pairing_code`/`qr_payload` (they're only in
// the `start` response) — this cache slot holds the last-known pair of the two so the
// dialog can still render them if it's closed and reopened while sharing stays active.
// Never fetched itself (`enabled: false`) — only ever written via `setQueryData` below.
const LAN_SHARE_DETAILS_KEY = ['notes', LAN_CHANNEL, 'share-details']

export interface LanShareDetails {
  pairing_code: string
  qr_payload: Record<string, unknown>
}

export function getLanShareStatus() {
  return api.get<LanShareStatus>('/notes/lan/share/status')
}

export function startLanShare() {
  return api.post<LanShareStartResult>('/notes/lan/share/start')
}

export function stopLanShare() {
  return api.post<LanShareStopResult>('/notes/lan/share/stop')
}

/** Polls sharing status — `enabled` lets the pairing dialog only poll while it's open, and
 * polling speeds up to 2s while actively sharing (so the QR/code panel reflects a stop
 * triggered elsewhere, or an IP change) vs. a slower idle poll otherwise. */
export function useLanShareStatus(enabled: boolean) {
  return useQuery({
    queryKey: LAN_SHARE_STATUS_KEY,
    queryFn: getLanShareStatus,
    enabled,
    refetchInterval: (query) => (query.state.data?.sharing ? 2000 : 5000),
  })
}

/** Reads back the last-known pairing code/QR payload from cache — see
 * `LAN_SHARE_DETAILS_KEY` above. `enabled: false` means it's never fetched itself, only
 * ever populated by `useStartLanShare`'s `onSuccess`; this hook just gives the dialog a
 * reactive read of that cache slot across its own mount/unmount. */
export function useLanShareDetails() {
  return useQuery<LanShareDetails | null>({
    queryKey: LAN_SHARE_DETAILS_KEY,
    queryFn: () => Promise.resolve(null),
    enabled: false,
    initialData: null,
  })
}

/** Starts LAN sharing (spins up the sidecar's local HTTP server + returns the QR payload
 * and 6-digit code). Failure (e.g. port unavailable) is a normal `ApiError` with a `detail`
 * message — the dialog surfaces it inline rather than a toast, since it's the one place the
 * user needs to act on it right away. */
export function useStartLanShare() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: startLanShare,
    onSuccess: (result) => {
      queryClient.setQueryData(LAN_SHARE_STATUS_KEY, {
        sharing: true,
        lan_port: result.lan_port,
        host_ips: result.host_ips,
      } satisfies LanShareStatus)
      queryClient.setQueryData(LAN_SHARE_DETAILS_KEY, {
        pairing_code: result.pairing_code,
        qr_payload: result.qr_payload,
      } satisfies LanShareDetails)
    },
  })
}

/** Stops LAN sharing. Only ever called by an explicit user action ("Stop sharing") — sharing
 * persists across dialog close/reopen until the user stops it themselves. */
export function useStopLanShare() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: stopLanShare,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LAN_SHARE_STATUS_KEY })
      queryClient.setQueryData(LAN_SHARE_DETAILS_KEY, null)
    },
    onError: () => toast.error('Could not stop device sync'),
  })
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import type { ContinuityFlag, ContinuityStatus } from '@/lib/api'

/** Fetches this Book's continuity flags, optionally filtered to one `status` (docs/03
 * `continuity_flags`, docs/06 Phase 4). */
export function useContinuityFlags(bookId: string | undefined, status?: ContinuityStatus) {
  return useQuery({
    queryKey: ['continuity', bookId, status],
    queryFn: () =>
      api.get<ContinuityFlag[]>(
        `/books/${bookId}/continuity/flags${status ? `?status=${status}` : ''}`,
      ),
    enabled: !!bookId,
  })
}

export interface RunContinuityInput {
  includeAi?: boolean
}

/** Runs the continuity check for this Book — deterministic rules always, AI checks
 * only if `includeAi` is set (docs/06 Phase 4; AI path never runs on this machine). */
export function useRunContinuity(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ includeAi }: RunContinuityInput = {}) =>
      api.post<ContinuityFlag[]>(
        `/books/${bookId}/continuity/check?include_ai=${includeAi ?? false}`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['continuity', bookId] })
    },
    onError: () => toast.error('Could not run the continuity check'),
  })
}

export interface UpdateFlagInput {
  id: string
  status: ContinuityStatus
}

/** Patches one continuity flag's status (open/dismissed/resolved). */
export function useUpdateFlag(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UpdateFlagInput) =>
      api.patch<ContinuityFlag>(`/continuity/flags/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['continuity', bookId] })
    },
    onError: () => toast.error('Could not update the flag'),
  })
}

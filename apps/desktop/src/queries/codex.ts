import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import type { CodexEntry, CodexEntryType } from '@/lib/api'

/** Fetches Codex entries, optionally filtered to one `entry_type` (docs/03 `codex_entries`,
 * docs/06 Phase 2 task H3). Entries are canonical — shared across every Book, like Scene. */
export function useCodexEntries(entryType?: CodexEntryType) {
  return useQuery({
    queryKey: ['codex', entryType ?? 'all'],
    queryFn: () =>
      api.get<CodexEntry[]>(`/codex${entryType ? `?entry_type=${entryType}` : ''}`),
  })
}

export interface CreateCodexInput {
  entry_type: CodexEntryType
  name: string
  summary?: string | null
  custom_fields?: Record<string, unknown> | null
}

/** Creates a Codex entry. The full custom-fields/relationships/arc editor is Phase 3
 * (docs/06) — this MVP only ever sends name + summary. */
export function useCreateCodex() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateCodexInput) => api.post<CodexEntry>('/codex', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['codex'] })
    },
    onError: () => toast.error('Could not create the codex entry'),
  })
}

export interface UpdateCodexInput {
  id: string
  name?: string
  summary?: string | null
  custom_fields?: Record<string, unknown> | null
}

/** Patches a Codex entry (name/summary only in this MVP). */
export function useUpdateCodex() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UpdateCodexInput) => api.patch<CodexEntry>(`/codex/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['codex'] })
    },
    onError: () => toast.error('Could not update the codex entry'),
  })
}

/** Deletes a Codex entry permanently — everywhere it's linked (all Scenes/Books). */
export function useDeleteCodex() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/codex/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['codex'] })
      queryClient.invalidateQueries({ queryKey: ['scene-codex'] })
      toast.success('Codex entry deleted')
    },
    onError: () => toast.error('Could not delete the codex entry'),
  })
}

/** Fetches the Codex entries linked to one Scene (the canvas node currently selected). */
export function useSceneCodex(sceneId: string | undefined) {
  return useQuery({
    queryKey: ['scene-codex', sceneId],
    queryFn: () => api.get<CodexEntry[]>(`/scenes/${sceneId}/codex`),
    enabled: !!sceneId,
  })
}

/** Links a Codex entry onto one Scene. */
export function useLinkCodexToScene(sceneId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (entryId: string) => api.post<CodexEntry>(`/codex/${entryId}/scenes/${sceneId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-codex', sceneId] })
    },
    onError: () => toast.error('Could not link the codex entry to this scene'),
  })
}

/** Unlinks a Codex entry from one Scene. The entry itself survives everywhere else. */
export function useUnlinkCodexFromScene(sceneId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (entryId: string) => api.delete(`/codex/${entryId}/scenes/${sceneId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-codex', sceneId] })
    },
    onError: () => toast.error('Could not unlink the codex entry from this scene'),
  })
}

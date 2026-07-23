import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError, API_BASE } from '@/lib/api'
import type { CodexArcState, CodexEntry, CodexEntryType, CodexRelationship, ImageRead } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

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
  primary_image_id?: string | null
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

// ── Codex relationships (docs/06 Phase 3 Codex). ──

/** Fetches all relationships touching one Codex entry, in either direction. */
export function useCodexRelationships(entryId?: string) {
  return useQuery({
    queryKey: ['codex-relationships', entryId],
    queryFn: () => api.get<CodexRelationship[]>(`/codex/${entryId}/relationships`),
    enabled: !!entryId,
  })
}

export interface CreateRelationshipInput {
  entryId: string
  to_entry_id: string
  relationship_type: string
  description?: string | null
}

/** Creates a relationship from one Codex entry to another. */
export function useCreateRelationship() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, ...body }: CreateRelationshipInput) =>
      api.post<CodexRelationship>(`/codex/${entryId}/relationships`, body),
    onSuccess: (_data, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: ['codex-relationships', entryId] })
    },
    onError: () => toast.error('Could not create the relationship'),
  })
}

/** Deletes a relationship. `entryId` is passed through only to invalidate the right cache key. */
export function useDeleteRelationship() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ relId }: { relId: string; entryId: string }) =>
      api.delete(`/codex/relationships/${relId}`),
    onSuccess: (_data, { entryId }) => {
      queryClient.invalidateQueries({ queryKey: ['codex-relationships', entryId] })
    },
    onError: () => toast.error('Could not delete the relationship'),
  })
}

// ── Codex arc states (docs/06 Phase 3 Codex). ──

/** Fetches the arc-state timeline for one Codex entry, optionally scoped to one Book. */
export function useCodexArcStates(entryId?: string, bookId?: string) {
  return useQuery({
    queryKey: ['codex-arc-states', entryId, bookId],
    queryFn: () =>
      api.get<CodexArcState[]>(
        `/codex/${entryId}/arc-states${bookId ? `?book_id=${bookId}` : ''}`,
      ),
    enabled: !!entryId,
  })
}

export interface CreateArcStateInput {
  entryId: string
  book_id: string
  as_of_outline_order_index: number
  status_summary?: string | null
  traits_snapshot?: Record<string, unknown> | null
}

/** Records a new arc state (a point-in-time snapshot) for one Codex entry. */
export function useCreateArcState() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, ...body }: CreateArcStateInput) =>
      api.post<CodexArcState>(`/codex/${entryId}/arc-states`, body),
    onSuccess: (_data, { entryId, book_id }) => {
      queryClient.invalidateQueries({ queryKey: ['codex-arc-states', entryId, book_id] })
      queryClient.invalidateQueries({ queryKey: ['codex-arc-states', entryId, undefined] })
    },
    onError: () => toast.error('Could not record the arc state'),
  })
}

/** Deletes an arc state. `entryId`/`bookId` are passed through only to invalidate the right cache key. */
export function useDeleteArcState() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ arcStateId }: { arcStateId: string; entryId: string; bookId?: string }) =>
      api.delete(`/codex/arc-states/${arcStateId}`),
    onSuccess: (_data, { entryId, bookId }) => {
      queryClient.invalidateQueries({ queryKey: ['codex-arc-states', entryId, bookId] })
      queryClient.invalidateQueries({ queryKey: ['codex-arc-states', entryId, undefined] })
    },
    onError: () => toast.error('Could not delete the arc state'),
  })
}

// ── Images (docs/06 Phase 3 Codex). Upload is a RAW request body, not multipart/JSON —
// [SECURITY-REVIEW] mirrors the voice-note upload path; see docs/05 §uploads. ──

/** Builds a stable `<img src>` URL for an image by id. No fetch needed for display. */
export function imageUrl(id: string): string {
  return `${API_BASE}/images/${id}`
}

export interface UploadImageInput {
  file: File
  displayName?: string
}

/** Uploads an image as a raw byte-body PUT/POST (not multipart, not JSON — the sidecar
 * expects the file's raw bytes with a matching `Content-Type`, same pattern as voice-note
 * upload). Goes around the shared `api` client because that client always JSON-encodes. */
export function useUploadImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, displayName }: UploadImageInput) => {
      const token = useAuthStore.getState().token
      const params = new URLSearchParams({
        filename: file.name,
        display_name: displayName ?? file.name,
      })
      const res = await fetch(`${API_BASE}/images?${params.toString()}`, {
        method: 'POST',
        headers: {
          'Content-Type': file.type || 'application/octet-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: file,
      })
      if (!res.ok) {
        throw new ApiError(`POST /images → ${res.status}`, res.status)
      }
      return (await res.json()) as ImageRead
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
    onError: () => toast.error('Could not upload the image'),
  })
}

/** Attaches an already-uploaded image as a Codex entry's primary image (wraps the
 * existing PATCH /codex/{id} — no separate "attach" endpoint). */
export function useAttachImage() {
  return useUpdateCodex()
}

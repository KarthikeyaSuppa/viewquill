import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'

/** Mirrors app/models/schemas.py ScreenplayElementType (docs/03 `screenplay_elements`). */
export type ScreenplayElementType =
  | 'scene_heading'
  | 'action'
  | 'character'
  | 'dialogue'
  | 'parenthetical'
  | 'transition'
  | 'shot'
  | 'dual_dialogue'

/** Mirrors app/models/schemas.py ScreenplayElementRead. */
export interface ScreenplayElement {
  id: string
  scene_id: string
  order_index: number
  element_type: ScreenplayElementType
  text: string
}

/** Fetches one Scene's screenplay elements in order (script-type Books only). */
export function useElements(sceneId: string | undefined) {
  return useQuery({
    queryKey: ['elements', sceneId],
    queryFn: () => api.get<ScreenplayElement[]>(`/scenes/${sceneId}/elements`),
    enabled: !!sceneId,
  })
}

export interface CreateElementInput {
  element_type: ScreenplayElementType
  text: string
  order_index?: number
}

/** Appends a screenplay element to a Scene. NEVER touches the Scene's own `description`. */
export function useCreateElement(sceneId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateElementInput) =>
      api.post<ScreenplayElement>(`/scenes/${sceneId}/elements`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['elements', sceneId] })
    },
    onError: () => toast.error('Could not add the element'),
  })
}

export interface UpdateElementInput {
  id: string
  element_type?: ScreenplayElementType
  text?: string
  order_index?: number
}

/** Patches one screenplay element (type and/or text). */
export function useUpdateElement(sceneId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UpdateElementInput) =>
      api.patch<ScreenplayElement>(`/scenes/elements/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['elements', sceneId] })
    },
    onError: () => toast.error('Could not update the element'),
  })
}

/** Deletes one screenplay element permanently (the parent Scene is untouched). */
export function useDeleteElement(sceneId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (elementId: string) => api.delete(`/scenes/elements/${elementId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['elements', sceneId] })
    },
    onError: () => toast.error('Could not delete the element'),
  })
}

/** Reorders a Scene's elements — body is the full ordered list of element ids. */
export function useReorderElements(sceneId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (elementIds: string[]) =>
      api.post<ScreenplayElement[]>(`/scenes/${sceneId}/elements/reorder`, {
        element_ids: elementIds,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['elements', sceneId] })
    },
    onError: () => toast.error('Could not reorder the elements'),
  })
}

/** Mirrors app/models/schemas.py SceneRevisionRead (docs/03, PHASE11.md Workstream B's
 * scene-revision history) — a snapshot of a Scene's title/description/status taken on each
 * edit, newest-first. `change_source` distinguishes how the revision was produced
 * (`manual_edit`/`enhance_accept`/`ai_merge`/`restore`, per the backend's writers). Read-only
 * from the frontend today — nothing here creates or restores a revision. */
export interface SceneRevision {
  id: string
  revision_number: number
  title: string
  description: string | null
  status: string | null
  change_source: string
  parent_revision_id: string | null
  note: string | null
  created_at: string
}

/** Fetches one Scene's revision history, newest-first (server-sorted). Used by the canvas
 * node's ⋯ menu "History" item (`components/canvas/nodes.tsx`) — read-only, no restore
 * action exists yet (that needs its own backend endpoint). */
export function useSceneRevisions(sceneId: string | undefined) {
  return useQuery({
    queryKey: ['scene-revisions', sceneId],
    queryFn: () => api.get<SceneRevision[]>(`/scenes/${sceneId}/revisions`),
    enabled: !!sceneId,
  })
}

/** Deletes a Scene permanently — everywhere it's linked, including all its screenplay
 * elements. This is NOT the same as unlinking from one Book's canvas (see
 * useRemoveFromCanvas in queries/canvas.ts) — callers must keep the two visually and
 * textually distinct so a user never confuses "unlink" with "delete forever".
 *
 * Deliberately does NOT toast on success itself (unlike this file's other mutations) — the
 * backend now writes an `UndoLog` tombstone before deleting (PHASE11.md Workstream B task 7),
 * so every call site shows its own undo-able toast instead (`queries/undo.ts`'s
 * `showUndoToast`) rather than a plain "deleted" toast a caller can't attach an Undo action
 * to. Callers that don't need Undo (e.g. `node-editor.tsx`'s drawer-close delete) toast
 * themselves in their own `mutate(...)` `onSuccess`. */
export function useDeleteScene() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sceneId: string) => api.delete(`/scenes/${sceneId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas'] })
    },
    onError: () => toast.error('Could not delete the scene'),
  })
}

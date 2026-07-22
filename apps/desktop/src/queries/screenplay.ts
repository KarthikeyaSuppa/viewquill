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

/** Deletes a Scene permanently — everywhere it's linked, including all its screenplay
 * elements. This is NOT the same as unlinking from one Book's canvas (see
 * useRemoveFromCanvas in queries/canvas.ts) — callers must keep the two visually and
 * textually distinct so a user never confuses "unlink" with "delete forever". */
export function useDeleteScene() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sceneId: string) => api.delete(`/scenes/${sceneId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas'] })
      toast.success('Scene deleted permanently')
    },
    onError: () => toast.error('Could not delete the scene'),
  })
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import type { BookSceneOrder, Chapter, StructureTemplate } from '@/lib/api'

/** Fetches one Book's Outline rows (docs/03 `book_scene_order`, docs/06 Phase 4). */
export function useOutline(bookId: string | undefined) {
  return useQuery({
    queryKey: ['outline', bookId],
    queryFn: () => api.get<BookSceneOrder[]>(`/books/${bookId}/outline`),
    enabled: !!bookId,
  })
}

/** Fetches one Book's Timeline rows — same underlying row type as Outline, different ordering. */
export function useTimeline(bookId: string | undefined) {
  return useQuery({
    queryKey: ['timeline', bookId],
    queryFn: () => api.get<BookSceneOrder[]>(`/books/${bookId}/timeline`),
    enabled: !!bookId,
  })
}

export interface AssignSceneInput {
  sceneId: string
  chapter_id?: string | null
  structure_beat?: string | null
  outline_order_index?: number
}

/** Assigns a Scene to a Chapter/structure beat/outline position (docs/06 Phase 4). */
export function useAssignScene(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sceneId, ...body }: AssignSceneInput) =>
      api.post<BookSceneOrder>(`/books/${bookId}/scenes/${sceneId}/assign`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['outline', bookId] })
    },
    onError: () => toast.error('Could not assign the scene'),
  })
}

/** Reorders the Outline — body is the full ordered list of scene ids. */
export function useReorderOutline(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sceneIds: string[]) =>
      api.post<BookSceneOrder[]>(`/books/${bookId}/outline/reorder`, { scene_ids: sceneIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['outline', bookId] })
    },
    onError: () => toast.error('Could not reorder the outline'),
  })
}

export interface SetTimelineInput {
  sceneId: string
  timeline_order_index?: number
  in_story_time_label?: string | null
  in_story_time_sort_key?: number | null
}

/** Sets one Scene's in-story-time placement on the Timeline. */
export function useSetTimeline(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sceneId, ...body }: SetTimelineInput) =>
      api.post<BookSceneOrder>(`/books/${bookId}/scenes/${sceneId}/timeline`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timeline', bookId] })
    },
    onError: () => toast.error('Could not update the timeline'),
  })
}

/** Reorders the Timeline — body is the full ordered list of scene ids. */
export function useReorderTimeline(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sceneIds: string[]) =>
      api.post<BookSceneOrder[]>(`/books/${bookId}/timeline/reorder`, { scene_ids: sceneIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timeline', bookId] })
    },
    onError: () => toast.error('Could not reorder the timeline'),
  })
}

/** Fetches one Book's Chapters, in order. */
export function useChapters(bookId: string | undefined) {
  return useQuery({
    queryKey: ['chapters', bookId],
    queryFn: () => api.get<Chapter[]>(`/books/${bookId}/chapters`),
    enabled: !!bookId,
  })
}

export interface CreateChapterInput {
  title: string
  order_index?: number
}

/** Creates a new Chapter on this Book. */
export function useCreateChapter(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateChapterInput) =>
      api.post<Chapter>(`/books/${bookId}/chapters`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chapters', bookId] })
    },
    onError: () => toast.error('Could not create the chapter'),
  })
}

export interface UpdateChapterInput {
  id: string
  title?: string
  order_index?: number
}

/** Patches a Chapter's title and/or order. */
export function useUpdateChapter(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UpdateChapterInput) =>
      api.patch<Chapter>(`/chapters/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chapters', bookId] })
    },
    onError: () => toast.error('Could not update the chapter'),
  })
}

/** Deletes a Chapter permanently. Scenes assigned to it are not deleted (backend contract). */
export function useDeleteChapter(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (chapterId: string) => api.delete(`/chapters/${chapterId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chapters', bookId] })
      queryClient.invalidateQueries({ queryKey: ['outline', bookId] })
    },
    onError: () => toast.error('Could not delete the chapter'),
  })
}

/** Fetches the structure templates applicable to one Book type (or all, if omitted). */
export function useStructureTemplates(bookType?: string) {
  return useQuery({
    queryKey: ['structure-templates', bookType],
    queryFn: () =>
      api.get<StructureTemplate[]>(
        `/structure-templates${bookType ? `?book_type=${bookType}` : ''}`,
      ),
  })
}

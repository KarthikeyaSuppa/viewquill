import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import type {
  CanvasEdge,
  CanvasNode,
  CanvasResponse,
  ConnectionType,
  NodeType,
  Scene,
} from '@/lib/api'

/** Fetches one Book's canvas (nodes = Scene links + layout, edges = graph connections). */
export function useCanvas(bookId: string | undefined) {
  return useQuery({
    queryKey: ['canvas', bookId],
    queryFn: () => api.get<CanvasResponse>(`/books/${bookId}/canvas`),
    enabled: !!bookId,
  })
}

export interface CreateNodeInput {
  node_type: NodeType
  title: string
  description?: string | null
  canvas_x?: number
  canvas_y?: number
}

/** Creates a new canonical Scene, then links it onto this Book's canvas at a position. */
export function useCreateNode(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ node_type, title, description, canvas_x, canvas_y }: CreateNodeInput) => {
      if (!bookId) throw new Error('No book id')
      const scene = await api.post<Scene>('/scenes', { node_type, title, description })
      return api.post<CanvasNode>(`/books/${bookId}/scenes/${scene.id}`, { canvas_x, canvas_y })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not add the node'),
  })
}

export interface UpdateNodePositionInput {
  sceneId: string
  canvas_x: number
  canvas_y: number
}

/** Patches a Book-link's layout (position). Intended to be called debounced from drag. */
export function useUpdateNodePosition(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ sceneId, canvas_x, canvas_y }: UpdateNodePositionInput) =>
      api.patch<CanvasNode>(`/books/${bookId}/scenes/${sceneId}`, { canvas_x, canvas_y }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not save the node position'),
  })
}

export interface UpdateSceneInput {
  id: string
  title?: string
  description?: string | null
  status?: string | null
}

/** Patches the canonical Scene's title/description/status (shared across every Book it's on). */
export function useUpdateScene(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UpdateSceneInput) => api.patch<Scene>(`/scenes/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not update the scene'),
  })
}

/** Unlinks a Scene from this Book's canvas. The Scene itself is untouched and survives. */
export function useRemoveFromCanvas(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sceneId: string) => api.delete(`/books/${bookId}/scenes/${sceneId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
      toast.success('Removed from canvas — the scene itself is safe')
    },
    onError: () => toast.error('Could not remove the node from the canvas'),
  })
}

export interface CreateEdgeInput {
  source_scene_id: string
  target_scene_id: string
  source_handle?: string | null
  target_handle?: string | null
  connection_type?: ConnectionType | null
  label?: string | null
  sequence_weight?: number | null
}

export function useCreateEdge(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateEdgeInput) => api.post<CanvasEdge>(`/books/${bookId}/edges`, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not connect the nodes'),
  })
}

export interface UpdateEdgeInput {
  connection_type?: ConnectionType | null
  source_scene_id?: string
  target_scene_id?: string
  source_handle?: string | null
  target_handle?: string | null
  label?: string | null
}

export function useUpdateEdge(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ edgeId, ...body }: { edgeId: string } & UpdateEdgeInput) =>
      api.patch<CanvasEdge>(`/edges/${edgeId}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not update the connection'),
  })
}

export function useDeleteEdge(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (edgeId: string) => api.delete(`/edges/${edgeId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Could not remove the connection'),
  })
}

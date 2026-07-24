import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError, API_BASE } from '@/lib/api'
import type { EntityImageEntityType, EntityImageRead, ImageBucket, ImageRead } from '@/lib/api'
import { useAuthStore } from '@/stores/auth'

/**
 * Image query hooks (docs/06 Phase 5 task FE-A) — the reference-pool gallery + the
 * Book-scoped export-preview. Supersedes/duplicates a couple of narrower hooks already in
 * `src/queries/codex.ts` (that file's `useUploadImage`/`imageUrl` stay put, wired to the
 * Codex-entry primary-image picker — not touched here); this file is the fuller Phase 5 set.
 *
 * `GET /images/{id}` and `/images/{id}/thumb` are unauthenticated on the sidecar (no
 * `Depends` auth check in app/api/images.py, and app/main.py has no global auth middleware —
 * confirmed by reading both) — so a plain `<img src>` works and we don't need to fetch bytes
 * into a blob/object URL just to attach a Bearer header.
 */

/** Builds a stable `<img src>` URL for an image's full bytes. No fetch/auth needed. */
export function imageUrl(id: string): string {
  return `${API_BASE}/images/${id}`
}

/** Builds a stable `<img src>` URL for an image's thumbnail bytes. */
export function imageThumbUrl(id: string): string {
  return `${API_BASE}/images/${id}/thumb`
}

/** Fetches images, optionally filtered by bucket/tag/search query (docs/03 `images`). */
export function useImages(bucket?: ImageBucket, q?: string, tag?: string) {
  return useQuery({
    queryKey: ['images', bucket ?? 'all', q ?? '', tag ?? ''],
    queryFn: () => {
      const params = new URLSearchParams()
      if (bucket) params.set('bucket', bucket)
      if (q) params.set('q', q)
      if (tag) params.set('tag', tag)
      const query = params.toString()
      return api.get<ImageRead[]>(`/images${query ? `?${query}` : ''}`)
    },
  })
}

/** Fetches exactly the images a Book's export will bundle (docs/06 Phase 5 task BE-3) —
 * images attached to the Book itself, to any Scene on its canvas, or to any Codex entry
 * linked to those scenes. Read-only preview; nothing here can be edited from this hook. */
export function useBookImages(bookId: string | undefined) {
  return useQuery({
    queryKey: ['book-images', bookId],
    queryFn: () => api.get<ImageRead[]>(`/books/${bookId}/images`),
    enabled: !!bookId,
  })
}

export interface UploadImageInput {
  file: File
  bucket?: ImageBucket
  displayName?: string
}

/** Uploads an image as a raw byte-body POST (not multipart, not JSON — the sidecar expects
 * the file's raw bytes with a matching `Content-Type`; metadata rides along as query params).
 * Goes around the shared `api` client because that client always JSON-encodes.
 * [SECURITY-REVIEW] rides on this path per CLAUDE.md — mirrors the voice-note upload
 * (`src/queries/voice.ts`) and the existing `useUploadImage` in `src/queries/codex.ts`. */
export function useUploadImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, bucket, displayName }: UploadImageInput) => {
      const token = useAuthStore.getState().token
      const params = new URLSearchParams({
        filename: file.name,
        display_name: displayName ?? file.name,
        ...(bucket ? { bucket } : {}),
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
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 413) {
        toast.error('That image is too large (10MB max).')
      } else if (error instanceof ApiError && error.status === 415) {
        toast.error('Unsupported image type — use PNG, JPEG, WebP, or GIF.')
      } else if (error instanceof ApiError && error.status === 422) {
        toast.error('That file could not be read as an image.')
      } else {
        toast.error('Could not upload the image')
      }
    },
  })
}

export interface UpdateImageInput {
  id: string
  display_name?: string
  description?: string | null
}

/** Patches an image's display name and/or description. */
export function useUpdateImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: UpdateImageInput) => api.patch<ImageRead>(`/images/${id}`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['images'] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
    },
    onError: () => toast.error('Could not update the image'),
  })
}

/** Deletes an image permanently — everywhere it's referenced/linked. */
export function useDeleteImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/images/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['images'] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
      toast.success('Image deleted')
    },
    onError: () => toast.error('Could not delete the image'),
  })
}

/** Adds a tag to an image. Empty tags are rejected by the sidecar (422). */
export function useAddTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, tag }: { id: string; tag: string }) =>
      api.post<ImageRead>(`/images/${id}/tags`, { tag }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['images'] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
    },
    onError: () => toast.error('Could not add the tag'),
  })
}

/** Removes a tag from an image. A no-op (204) if the tag wasn't present. */
export function useRemoveTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, tag }: { id: string; tag: string }) =>
      api.delete(`/images/${id}/tags/${encodeURIComponent(tag)}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['images'] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
    },
    onError: () => toast.error('Could not remove the tag'),
  })
}

// ── Polymorphic entity attach/detach (docs/03 `entity_images`; docs/06 Phase 5 task BE-3).
// Not used by this task's UI (the Images tab + gallery) — kept here ready for FE-B's
// image-detail dialog (attach-to-canvas-node, book-cover picker, etc). ──

export interface AttachImageInput {
  imageId: string
  entity_type: EntityImageEntityType
  entity_id: string
  role?: string | null
}

/** Attaches an already-uploaded image to a book/scene/codex_entry (many-to-many — distinct
 * from single-slot pointers like Codex's `primary_image_id`). */
export function useAttachImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ imageId, ...body }: AttachImageInput) =>
      api.post<EntityImageRead>(`/images/${imageId}/links`, body),
    onSuccess: (_data, { entity_type, entity_id }) => {
      queryClient.invalidateQueries({ queryKey: ['entity-images', entity_type, entity_id] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
    },
    onError: () => toast.error('Could not attach the image'),
  })
}

export interface DetachImageInput {
  imageId: string
  entity_type: EntityImageEntityType
  entity_id: string
  role?: string | null
}

/** Detaches an image from a book/scene/codex_entry. 204 either way (idempotent no-op if the
 * link doesn't/no-longer exists). */
export function useDetachImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ imageId, entity_type, entity_id, role }: DetachImageInput) => {
      const params = new URLSearchParams({ entity_type, entity_id })
      if (role) params.set('role', role)
      return api.delete(`/images/${imageId}/links?${params.toString()}`)
    },
    onSuccess: (_data, { entity_type, entity_id }) => {
      queryClient.invalidateQueries({ queryKey: ['entity-images', entity_type, entity_id] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
    },
    onError: () => toast.error('Could not detach the image'),
  })
}

/** Fetches the images attached to one entity (a Book, Scene, or Codex entry). */
export function useEntityImages(entityType: EntityImageEntityType | undefined, entityId: string | undefined) {
  return useQuery({
    queryKey: ['entity-images', entityType, entityId],
    queryFn: () => api.get<ImageRead[]>(`/entities/${entityType}/${entityId}/images`),
    enabled: !!entityType && !!entityId,
  })
}

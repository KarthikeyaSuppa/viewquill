import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError, API_BASE } from '@/lib/api'

/**
 * Export/draft-version query hooks (docs/06 Phase 6 task FE-1). Mirrors the shape of
 * `src/queries/images.ts` / `src/queries/books.ts`: hand-mirrored request/response types
 * (no query file in this codebase imports `@quillnight/api-types` directly yet — types are
 * hand-duplicated from `packages/api-types/schema.d.ts` / `app/models/schemas.py`, same
 * convention `books.ts` already uses for `BookType`/`Book`), `useQuery`/`useMutation` from
 * TanStack Query, `toast` from `sonner` on error/success, `queryClient.invalidateQueries` on
 * mutation success.
 *
 * Both `/books/{book_id}/export/{format}` and `/books/{book_id}/draft-versions` and
 * `/draft-versions/{id}/download` are unauthenticated on the sidecar (no `Depends` auth check
 * in app/api/export.py — confirmed by grepping `get_current_user`, which only appears in
 * `/auth` and `/settings`) — same situation as `/images`.
 */

export type ExportFormat = 'markdown' | 'docx' | 'pdf' | 'fountain' | 'fdx'

/** Mirrors app/models/schemas.py DraftVersionRead / packages/api-types/schema.d.ts
 * `components['schemas']['DraftVersionRead']`. */
export interface DraftVersionRead {
  id: string
  book_id: string
  version_number: number
  format: ExportFormat
  format_settings: Record<string, unknown> | null
  is_current: boolean
  generated_at: string
  notes: string | null
}

/** Lists a Book's draft versions, newest `version_number` first (server-sorted). */
export function useDraftVersions(bookId: string | undefined) {
  return useQuery({
    queryKey: ['draft-versions', bookId],
    queryFn: () => api.get<DraftVersionRead[]>(`/books/${bookId}/draft-versions`),
    enabled: !!bookId,
  })
}

/** Compiles a new export for a Book in the given format, creating a new `DraftVersionRead`
 * row. On an unsupported format for the Book's type the sidecar returns 422 with
 * `detail: "FORMAT_NOT_SUPPORTED_FOR_BOOK_TYPE"` — surfaced as a specific toast, mirroring how
 * `useUploadImage` (src/queries/images.ts) maps its own known status codes to plain-language
 * toasts instead of a generic failure message. Note: the shared `ApiError` (src/lib/api.ts)
 * only carries the HTTP status, not the response body's `detail` text, so — same as
 * `useUploadImage` — the mapping below is by status code alone; this endpoint's only
 * documented 422 case is the unsupported-format one. */
export function useCompileExport(bookId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (format: ExportFormat) =>
      api.post<DraftVersionRead>(`/books/${bookId}/export/${format}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['draft-versions', bookId] })
      toast.success('Export compiled')
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 422) {
        toast.error("This format isn't available for this book type")
      } else {
        toast.error('Could not compile the export')
      }
    },
  })
}

/** Builds a stable download URL for a draft version's raw file. No fetch/auth needed — meant
 * for a plain `<a href>`/`window.open`, not a JSON fetch (mirrors `imageUrl()`/
 * `imageThumbUrl()` in src/queries/images.ts). The sidecar sets the filename via
 * `Content-Disposition`. */
export function draftDownloadUrl(draftVersionId: string): string {
  return `${API_BASE}/draft-versions/${draftVersionId}/download`
}

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Draft preview query hook. Mirrors the hand-mirrored-type convention already used by
 * `src/queries/export.ts`/`src/queries/outline.ts` (no query file in this codebase imports
 * `@quillnight/api-types` directly yet) — types below are hand-duplicated from
 * `app/models/schemas.py` `DraftPreviewOut`/`CompiledChapterPreviewOut`/
 * `CompiledScenePreviewOut`/`ScreenplayElementPreviewOut`, confirmed against the regenerated
 * `packages/api-types/schema.d.ts`.
 *
 * `GET /books/{book_id}/draft-preview` is read-only: it writes no file and creates no
 * `draft_versions` row (see app/api/draft_preview.py) — this is purely a "read back the
 * currently compiled manuscript" hook for a future manuscript-reader UI, not part of the
 * export pipeline in src/queries/export.ts.
 */

export interface ScreenplayElementPreviewOut {
  element_type: string
  text: string
  order_index: number
}

export interface CompiledScenePreviewOut {
  title: string
  description: string
  elements: ScreenplayElementPreviewOut[]
}

export interface CompiledChapterPreviewOut {
  title: string | null
  scenes: CompiledScenePreviewOut[]
}

export interface DraftPreviewOut {
  book_id: string
  book_title: string
  book_type: string
  logline: string | null
  front_matter: Record<string, unknown> | null
  cover_image_id: string | null
  chapters: CompiledChapterPreviewOut[]
}

/** Fetches the current, fully-compiled preview of one Book's manuscript (no file written,
 * no `draft_versions` row created — a read-only mirror of what `/export/{format}` would
 * compile). */
export function useDraftPreview(bookId: string | undefined) {
  return useQuery({
    queryKey: ['draft-preview', bookId],
    queryFn: () => api.get<DraftPreviewOut>(`/books/${bookId}/draft-preview`),
    enabled: !!bookId,
  })
}

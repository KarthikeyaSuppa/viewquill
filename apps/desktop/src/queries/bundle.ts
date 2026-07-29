import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError } from '@/lib/api'

/**
 * `.quillproj` export/import query hooks (docs/06 Phase 7, final task). Mirrors
 * `src/queries/export.ts`'s shape (hand-duplicated types from
 * `app/models/schemas.py`/`packages/api-types/schema.d.ts` — `MergeReport`/`EntityChange`/
 * `EntityConflict` aren't present in the generated schema yet, so these are declared here
 * directly), but the transport is different: export returns raw encrypted bytes
 * (`api.postBlob`) and import inspect/apply take the bundle bytes as a raw request body
 * plus an `X-Quillnight-Passphrase` header (`api.postRaw`) — see `src/lib/api.ts`.
 */

export interface EntityChange {
  table: string
  id: string
  name: string
}

export interface EntityConflict {
  table: string
  id: string
  name: string
  differing_fields: string[]
}

export interface MergeReport {
  schema_version: number
  book_id: string
  created: EntityChange[]
  matched: EntityChange[]
  conflicts: EntityConflict[]
  asset_warnings: string[]
}

export type ConflictResolution = 'keep_local' | 'take_imported' | 'merge'

const PASSPHRASE_HEADER = 'X-Quillnight-Passphrase'

/** Encrypts and downloads a Book's full `.quillproj` backup. Triggers a browser download
 * (object URL + throwaway anchor click, revoked immediately after) rather than returning
 * the blob to the caller — the dialog only needs to know success/failure. */
export function useExportBundle(bookId: string) {
  return useMutation({
    mutationFn: async (passphrase: string) => {
      const { blob, filename } = await api.postBlob(`/books/${bookId}/export/bundle`, {
        passphrase,
      })
      return { blob, filename: filename ?? `book-${bookId}.quillproj` }
    },
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      toast.success('Backup exported')
    },
    onError: (error) => {
      toast.error(error instanceof ApiError && error.detail ? error.detail : 'Could not export the backup')
    },
  })
}

/** Inspects a `.quillproj` file against the current library without writing anything —
 * returns the `MergeReport` the review dialog renders (new/matched/conflicting entities,
 * asset warnings). No toast here: wrong-passphrase/corrupt-file errors are common and
 * surfaced inline in the dialog, not as a transient toast. */
export function useInspectBundle() {
  return useMutation({
    mutationFn: async ({ file, passphrase }: { file: File; passphrase: string }) => {
      const body = await file.arrayBuffer()
      return api.postRaw<MergeReport>('/import/quillproj/inspect', body, {
        [PASSPHRASE_HEADER]: passphrase,
      })
    },
  })
}

/** Applies a `.quillproj` import with the caller's per-conflict resolutions (composite
 * keys like `image_tags` use `"<image_id>|<tag>"`, unused here since the review dialog only
 * surfaces plain-`id` conflicts). Never silently overwrites — conflicts default to
 * `keep_local` server-side unless the caller explicitly resolves otherwise. On success,
 * invalidates the books list so any newly-created/updated Book appears immediately
 * (mirrors `useCreateBook`/`useConvertBook` in `src/queries/books.ts`). */
export function useApplyBundle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      file,
      passphrase,
      resolutions,
    }: {
      file: File
      passphrase: string
      resolutions: Record<string, ConflictResolution>
    }) => {
      const body = await file.arrayBuffer()
      return api.postRaw<MergeReport>(
        '/import/quillproj/apply',
        body,
        { [PASSPHRASE_HEADER]: passphrase },
        { resolutions: JSON.stringify(resolutions) },
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['books'] })
      toast.success('Backup imported')
    },
  })
}

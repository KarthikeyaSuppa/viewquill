import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api, ApiError } from '@/lib/api'
import type { CanvasResponse } from '@/lib/api'

/**
 * Canvas templates — "start from a template" on the empty canvas (docs/06 Phase 9 task 5,
 * docs/14-DEFERRED-ENHANCEMENTS.md). `POST /books/{book_id}/canvas/apply-template` isn't in
 * the generated `packages/api-types/schema.d.ts` yet (would need `npm run gen:types` against
 * a running sidecar) — this mirrors `src/queries/bundle.ts`/`src/queries/backups.ts`'s
 * precedent of hand-declaring the shape locally rather than blocking on regeneration.
 * Matches `app/services/canvas_template_service.py` (`CANVAS_TEMPLATES` keys) and
 * `app/models/schemas.py::ApplyCanvasTemplateRequest`.
 */

export type CanvasTemplateKey = 'three_act' | 'heros_journey'

export interface ApplyCanvasTemplateInput {
  template_key: CanvasTemplateKey
}

/** Seeds a blank canvas from a built-in structure template. The backend guards this to
 * only ever apply to a genuinely empty canvas (409 if it already has nodes, a race the UI
 * only surfaces if the user double-clicks or another tab beat them to it — see
 * `canvas_template_service.py`'s `TemplateAlreadyAppliedError`). On success, invalidates the
 * same `['canvas', bookId]` query every other canvas mutation in `queries/canvas.ts`
 * invalidates, so the new nodes/edges appear immediately. */
export function useApplyCanvasTemplate(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ template_key }: ApplyCanvasTemplateInput) => {
      if (!bookId) throw new Error('No book id')
      return api.post<CanvasResponse>(`/books/${bookId}/canvas/apply-template`, { template_key })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.error('This canvas already has nodes on it — templates only apply to a blank canvas')
        queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
        return
      }
      toast.error('Could not apply the template')
    },
  })
}

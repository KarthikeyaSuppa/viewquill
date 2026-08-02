import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import type { UndoAction } from '@/lib/api'

/** Pops and re-applies the most recent `UndoLog` row for a Book — covers both
 * `delete_scene` (canvas-panel.tsx keyboard-delete, nodes.tsx "Delete permanently") and
 * `merge_scenes` (merge-dialog.tsx Accept) undo-able actions (PHASE11.md Workstream B task 7).
 * Scoped to the single last action, not a multi-level history stack. Same invalidation
 * convention as every other `queries/canvas.ts` mutation — a plain `['canvas', bookId]`
 * invalidate is enough for the restored scene/node to reappear from the next refetch. */
export function useUndoLastAction(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => {
      if (!bookId) throw new Error('No book id')
      return api.post<UndoAction>(`/books/${bookId}/undo`, {})
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Nothing to undo'),
  })
}

/** Mirrors `useUndoLastAction` for `POST /books/{book_id}/redo` — re-applies whatever the
 * last Undo just reversed. Only ever surfaced from the brief "Redo available" toast
 * `showUndoToast` below shows after a successful Undo click, not a standalone control. */
export function useRedoLastAction(bookId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => {
      if (!bookId) throw new Error('No book id')
      return api.post<UndoAction>(`/books/${bookId}/redo`, {})
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['canvas', bookId] })
    },
    onError: () => toast.error('Nothing to redo'),
  })
}

/** Shared toast-with-Undo-button helper (PHASE11.md Workstream B task 16 — "the
 * discoverability toast for [undoable actions] is a separate task, not yet built") — every
 * destructive/merge call site (canvas-panel.tsx keyboard-delete, nodes.tsx "Delete
 * permanently", merge-dialog.tsx Accept) calls this instead of a plain `toast.success` so the
 * Undo action is wired identically everywhere, matching sonner's own
 * `toast.success(message, { action })` API rather than building a custom toast manager (sonner
 * already handles stacking/dismissal on its own).
 *
 * `undo` is injected by the caller (usually `useUndoLastAction(bookId).mutate`) rather than
 * this helper calling the hook itself, since hooks can't be called from a plain function —
 * callers already have the mutation in scope from wiring their own toast.
 *
 * After a successful Undo, this swaps in a second, brief toast offering "Redo" — reusing the
 * same pattern rather than a persistent redo-chain UI, per this task's "last ONE action, not a
 * deep stack" scope. */
export function showUndoToast(message: string, undo: () => void, redo: () => void) {
  toast.success(message, {
    action: {
      label: 'Undo',
      onClick: () => {
        undo()
        toast.success('Undone', {
          action: {
            label: 'Redo',
            onClick: () => redo(),
          },
        })
      },
    },
  })
}

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { EnhanceDiff } from '@/components/canvas/enhance-diff'
import { useAcceptMergeScenes, useMergeScenesSuggestion, useMergeSuggestionParts } from '@/queries/merge'
import { showUndoToast, useRedoLastAction, useUndoLastAction } from '@/queries/undo'

export interface MergeSourceScene {
  id: string
  title: string
  description: string | null
}

export interface MergeDialogProps {
  bookId: string
  /** The scene ids being merged — always the ids `sourceScenes` below were built from. */
  sourceSceneIds: string[]
  /** Current title/description of each scene being merged, so the "original" side of the
   * diff can show what's actually being combined (canvas-panel.tsx already has this in its
   * `nodes` state — no extra fetch needed). */
  sourceScenes: MergeSourceScene[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Builds the "original" side of the Accept/Reject diff: the source scenes' current
 * title+description, labeled and concatenated so the reader can see exactly what's being
 * folded into one merged scene. */
function buildOriginalText(scenes: MergeSourceScene[]): string {
  return scenes
    .map((scene) => `## ${scene.title}\n${scene.description?.trim() || '(no description yet)'}`)
    .join('\n\n')
}

/** The AI-assisted multi-node merge review dialog (PHASE11.md Workstream B, "AI-assisted
 * multi-node merge reusing the Enhance seam exactly"). Streams one merge suggestion from
 * `useMergeScenesSuggestion` and renders it through the SAME `EnhanceDiff` Accept/Reject/Edit
 * component the single-scene Enhance feature uses (`node-editor.tsx`'s `DescriptionField`) —
 * per CLAUDE.md's "every AI transform is Accept/Reject, never silent" rule, this deliberately
 * does not fork a second diff UI.
 *
 * `EnhanceDiff` only ever diffs one field (description) — the merged TITLE half of the
 * model's `TITLE: ...\nDESCRIPTION:\n...` response is surfaced separately, in a plain editable
 * `Input` above the diff, since there's no second source string to diff a title against (the
 * source scenes each have their own title, not one shared "original title").
 *
 * DATA-SENSITIVE GUARANTEE (mirrors `EnhanceDiff`'s own): Accept is the only path that calls
 * `useAcceptMergeScenes` — Reject, or closing the dialog any other way, never writes anything;
 * the streamed suggestion just evaporates with the dialog. */
export function MergeDialog({ bookId, sourceSceneIds, sourceScenes, open, onOpenChange }: MergeDialogProps) {
  const suggestion = useMergeScenesSuggestion()
  const acceptMerge = useAcceptMergeScenes(bookId)
  const undoLastAction = useUndoLastAction(bookId)
  const redoLastAction = useRedoLastAction(bookId)
  const parts = useMergeSuggestionParts(suggestion.streamedText)

  const [mergedTitle, setMergedTitle] = useState('')
  const [titleDirty, setTitleDirty] = useState(false)
  const startedForRef = useRef<string | null>(null)

  const original = useMemo(() => buildOriginalText(sourceScenes), [sourceScenes])
  const sourceKey = sourceSceneIds.join(',')

  // Kick off the SSE stream once per dialog-open — keyed on the actual source scene set so
  // re-opening for a different selection starts a fresh suggestion, but re-renders while the
  // same dialog is open don't re-trigger it.
  useEffect(() => {
    if (!open) {
      startedForRef.current = null
      return
    }
    if (startedForRef.current === sourceKey) return
    startedForRef.current = sourceKey
    setMergedTitle('')
    setTitleDirty(false)
    suggestion.start({ book_id: bookId, scene_ids: sourceSceneIds })
    // suggestion.start/cancel are stable (useCallback with no deps) — only `open`/`sourceKey`
    // should actually re-trigger this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sourceKey, bookId, sourceSceneIds])

  // Cancel any in-flight stream the moment the dialog closes, so a slow/abandoned suggestion
  // never keeps streaming (or gets accepted) after the user has moved on.
  useEffect(() => {
    if (!open) suggestion.cancel()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // The title field tracks the model's live-streamed suggestion until the user edits it by
  // hand — same "don't fight the user's own edit" convention `EnhanceDiff`'s own `editedText`
  // uses once `editing` flips true.
  useEffect(() => {
    if (!titleDirty) setMergedTitle(parts.title)
  }, [parts.title, titleDirty])

  function handleAccept(finalDescription: string) {
    const title = mergedTitle.trim() || 'Merged scene'
    acceptMerge.mutate(
      { source_scene_ids: sourceSceneIds, merged_title: title, merged_description: finalDescription },
      {
        onSuccess: () => {
          onOpenChange(false)
          showUndoToast(
            `Merged into “${title}”`,
            () => undoLastAction.mutate(),
            () => redoLastAction.mutate(),
          )
        },
      },
    )
  }

  function handleReject() {
    suggestion.cancel()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (!next ? handleReject() : onOpenChange(next))}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{`Merge ${sourceSceneIds.length} scenes`}</DialogTitle>
          <DialogDescription>
            Review the AI-combined scene below, then Accept to replace the source scenes with it, or
            Reject to leave the canvas exactly as it is.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="merge-title">Merged title</Label>
          <Input
            id="merge-title"
            value={mergedTitle}
            onChange={(event) => {
              setTitleDirty(true)
              setMergedTitle(event.target.value)
            }}
            placeholder={suggestion.isStreaming ? 'Titling…' : 'Merged scene title'}
          />
        </div>

        <EnhanceDiff
          original={original}
          enhanced={parts.description}
          provider={suggestion.provider}
          isStreaming={suggestion.isStreaming}
          acceptPending={acceptMerge.isPending}
          streamingLabel="Merging…"
          reviewLabel="Review the merged scene"
          onAccept={handleAccept}
          onReject={handleReject}
        />

        {suggestion.error && (
          <p className="text-xs text-destructive">Merge suggestion failed: {suggestion.error}</p>
        )}
      </DialogContent>
    </Dialog>
  )
}

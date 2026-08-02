import { useEffect, useMemo, useState } from 'react'
import { diffWordsWithSpace } from 'diff'
import { Check, Loader2, Pencil, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import type { EnhanceProvider } from '@/queries/enhance'
import { playChime, startScribbleLoop, stopScribbleLoop, useDelight } from '@/lib/delight'

export interface EnhanceDiffProps {
  /** The user's text exactly as it stood before this Enhance run — never mutated here. */
  original: string
  /** The provider's suggestion so far (may be a partial string while `isStreaming`). */
  enhanced: string
  provider: EnhanceProvider | null
  isStreaming?: boolean
  /** True while the caller's own PATCH (the actual write) is in flight after Accept. */
  acceptPending?: boolean
  /** Overrides the "Enhancing…" label shown in the header while `isStreaming` is true —
   * lets other Accept/Reject callers built on this same component (e.g. the canvas
   * multi-node merge dialog, PHASE11.md task 11) show task-appropriate copy without
   * forking a duplicate component. Defaults to Enhance's own original copy. */
  streamingLabel?: string
  /** Overrides the "Review the suggestion" label shown once streaming completes — same
   * rationale as `streamingLabel`. */
  reviewLabel?: string
  /** The ONLY path in this component that hands text back to the caller. The caller is
   * expected to PATCH the real Scene/element with this text — this component itself
   * never calls a mutation. */
  onAccept: (finalText: string) => void
  /** Must never be paired with any write on the caller's side — closing/rejecting a
   * suggestion leaves the original text exactly as it was. */
  onReject: () => void
  onEditFurther?: (currentText: string) => void
}

/** Word-level Accept/Reject/Edit review affordance for one Enhance suggestion (docs/06
 * Phase 2 task H2, docs/04-LLM-INTEGRATION.md). Renders a `diffWordsWithSpace` comparison
 * of original → enhanced as a review affordance on the glass/panda chrome (not the
 * manuscript surface itself — the plain-text panels below still use `.manuscript`
 * typography so the words read naturally, but the diff coloring is chrome decoration).
 *
 * DATA-SENSITIVE GUARANTEE: Accept is the only button that calls back with text at all
 * (`onAccept`) — Reject and closing this panel call `onReject`, which the caller must
 * treat as a pure no-write dismissal. This component holds no mutation of its own. */
export function EnhanceDiff({
  original,
  enhanced,
  provider,
  isStreaming = false,
  acceptPending = false,
  streamingLabel = 'Enhancing…',
  reviewLabel = 'Review the suggestion',
  onAccept,
  onReject,
  onEditFurther,
}: EnhanceDiffProps) {
  const [editing, setEditing] = useState(false)
  const [editedText, setEditedText] = useState(enhanced)
  const { soundsOk, fireConfetti, fireDelightAccent } = useDelight()

  const parts = useMemo(() => diffWordsWithSpace(original, enhanced), [original, enhanced])

  // A soft "scribbling" texture loop while a suggestion is streaming in (docs/10 §5) —
  // started/stopped strictly around `isStreaming`, and only when sound is actually
  // allowed. Always stopped on unmount so a closed/dismissed panel never leaves a loop
  // running in the background.
  useEffect(() => {
    if (isStreaming && soundsOk) {
      startScribbleLoop()
    } else {
      stopScribbleLoop()
    }
    return () => stopScribbleLoop()
  }, [isStreaming, soundsOk])

  function handleEditFurther() {
    setEditedText(enhanced)
    setEditing(true)
    onEditFurther?.(enhanced)
  }

  function handleAccept() {
    if (soundsOk) playChime()
    // Not a `major` milestone — 'standard' stays confetti-only-for-major, so this only
    // actually fires at 'playful' (same tier `fireDelightAccent` requires).
    fireConfetti()
    fireDelightAccent()
    onAccept(editing ? editedText : enhanced)
  }

  const acceptDisabled =
    isStreaming || acceptPending || (editing ? editedText.trim().length === 0 : enhanced.length === 0)

  return (
    <div className="glass glass-edge flex flex-col gap-3 rounded-xl p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">
          {isStreaming ? streamingLabel : reviewLabel}
        </span>
        {provider && (
          <Badge variant="secondary" className="gap-1">
            {isStreaming && <Loader2 className="size-3 animate-spin" />}
            {provider === 'ollama' ? 'via local' : 'via Groq'}
          </Badge>
        )}
      </div>

      {editing ? (
        <Textarea
          className="manuscript min-h-24 text-sm"
          value={editedText}
          onChange={(event) => setEditedText(event.target.value)}
          autoFocus
        />
      ) : (
        <p className="manuscript min-h-[2lh] rounded-md p-2 text-sm leading-relaxed">
          {parts.map((part, index) => (
            <span
              key={index}
              className={cn(
                part.added &&
                  'rounded-sm bg-emerald-500/15 text-emerald-700 underline decoration-emerald-500/60 dark:text-emerald-300',
                part.removed &&
                  'rounded-sm bg-red-500/10 text-red-700/80 line-through decoration-red-500/50 dark:text-red-300/70',
              )}
            >
              {part.value}
            </span>
          ))}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={handleAccept} disabled={acceptDisabled} className="gap-1">
          <Check className="size-3.5" />
          {acceptPending ? 'Accepting…' : 'Accept'}
        </Button>
        <Button size="sm" variant="outline" onClick={onReject} disabled={acceptPending} className="gap-1">
          <X className="size-3.5" />
          Reject
        </Button>
        {!editing && (
          <Button
            size="sm"
            variant="ghost"
            onClick={handleEditFurther}
            disabled={isStreaming || acceptPending}
            className="gap-1"
          >
            <Pencil className="size-3.5" />
            Edit further
          </Button>
        )}
      </div>
    </div>
  )
}

import { useMemo, useState, type ReactNode } from 'react'
import { diffWordsWithSpace } from 'diff'
import { Copy, History } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { useSceneRevisions } from '@/queries/screenplay'

/** Badge label for `SceneRevision.change_source` — mirrors `nodes.tsx`'s own
 * `CHANGE_SOURCE_LABELS`. That map (and `formatRevisionTime` below) is module-local to
 * `nodes.tsx` (not exported), so this file keeps its own small copy rather than reaching
 * into another file's internals — same "small per-file formatting helper" convention
 * `nodes.tsx` itself calls out for `formatRevisionTime`. */
const CHANGE_SOURCE_LABELS: Record<string, string> = {
  manual_edit: 'Manual edit',
  enhance_accept: 'Enhance accepted',
  ai_merge: 'AI merge',
  restore: 'Restored',
}

function formatRevisionTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffMin = Math.round(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  const diffDay = Math.round(diffHour / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function copyToClipboard(text: string, label: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success(`Copied ${label}`),
    () => toast.error('Could not copy to clipboard'),
  )
}

/** Colors an old→new `diffWordsWithSpace` comparison using the EXACT classNames
 * `enhance-diff.tsx` uses (emerald = added, red/strikethrough = removed) so the same
 * visual language means the same thing everywhere in the app. */
function DiffBlock({ older, newer }: { older: string; newer: string }) {
  const parts = useMemo(() => diffWordsWithSpace(older, newer), [older, newer])
  if (older === newer) {
    return (
      <p className="manuscript rounded-md bg-muted/40 p-2 text-xs text-muted-foreground">No change.</p>
    )
  }
  return (
    <p className="manuscript rounded-md bg-muted/30 p-2 text-sm leading-relaxed">
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
  )
}

/** One version block: a small header (label + meta), the colored diff against the
 * previous snapshot, and a Copy button for THIS block's own "newer" text. Read-only —
 * no restore/edit action exists here (that would need its own backend endpoint, out of
 * scope for this task, same note `nodes.tsx`'s History popover already carries). */
function VersionBlock({
  header,
  older,
  newer,
  copyLabel,
}: {
  header: ReactNode
  older: string
  newer: string
  copyLabel: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        {header}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Copy ${copyLabel}`}
              onClick={() => copyToClipboard(newer, copyLabel)}
              disabled={newer.length === 0}
            >
              <Copy className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Copy {copyLabel}</TooltipContent>
        </Tooltip>
      </div>
      <DiffBlock older={older} newer={newer} />
    </div>
  )
}

/** "History" button + read-only Dialog (docs PHASE13 Workstream C task C4) — a
 * GitHub-style, version-by-version diff of one Scene's Description field. Reuses
 * `useSceneRevisions` (PHASE11.md Workstream B's append-only `scene_revisions` table) and
 * the exact diff coloring `enhance-diff.tsx` established, so Accept/Reject reviewing and
 * pure history-browsing read the same way visually. Purely read-only: no restore action,
 * mirroring `nodes.tsx`'s existing History popover (which shows a plain snippet, not a
 * diff) — this is the fuller Description-scoped version of that same read-only idea. */
export function DescriptionHistoryButton({
  sceneId,
  description,
}: {
  sceneId: string
  description: string
}) {
  const [open, setOpen] = useState(false)
  const { data: revisions, isLoading } = useSceneRevisions(open ? sceneId : undefined)

  const newest = revisions?.[0]
  // Shows what's changed since the last saved snapshot even before this session's edits
  // are saved — the "Unsaved changes" block below diffs the live `description` (which may
  // differ from what's on disk) against the newest revision on file, in addition to the
  // per-revision blocks that diff saved snapshots against each other.
  const hasUnsavedChanges = !!newest && description !== (newest.description ?? '')

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DialogTrigger asChild>
            <Button variant="ghost" size="sm" className="gap-1 text-xs">
              <History className="size-3.5" />
              History
            </Button>
          </DialogTrigger>
        </TooltipTrigger>
        <TooltipContent>Read-only version history for this Description</TooltipContent>
      </Tooltip>
      <DialogContent className="max-h-[80vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Description history</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !revisions || revisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No edit history yet.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {hasUnsavedChanges && (
              <VersionBlock
                header={
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs font-semibold text-foreground">Unsaved changes</span>
                    <Badge variant="secondary" className="text-[10px]">
                      since Rev {newest!.revision_number}
                    </Badge>
                  </div>
                }
                older={newest!.description ?? ''}
                newer={description}
                copyLabel="the current description"
              />
            )}

            {revisions.map((revision, index) => {
              const older = revisions[index + 1]?.description ?? ''
              const newer = revision.description ?? ''
              return (
                <VersionBlock
                  key={revision.id}
                  header={
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-xs font-semibold text-foreground">
                        Rev {revision.revision_number}
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        {CHANGE_SOURCE_LABELS[revision.change_source] ?? revision.change_source}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground">
                        {formatRevisionTime(revision.created_at)}
                      </span>
                    </div>
                  }
                  older={older}
                  newer={newer}
                  copyLabel={`Rev ${revision.revision_number}`}
                />
              )
            })}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Info,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useContinuityFlags, useRunContinuity, useUpdateFlag } from '@/queries/continuity'
import { useCanvas } from '@/queries/canvas'
import type { ContinuityFlag, ContinuitySeverity, ContinuityStatus } from '@/lib/api'
import { cn } from '@/lib/utils'

const SEVERITY_ORDER: ContinuitySeverity[] = ['critical', 'warning', 'hint']

/** Distinct severity tints, mirroring the emerald/red semantic-tint convention in
 * `enhance-diff.tsx` (inline Tailwind, no new tokens needed). */
const SEVERITY_META: Record<
  ContinuitySeverity,
  { label: string; badgeClass: string; icon: typeof AlertTriangle }
> = {
  critical: {
    label: 'Critical',
    badgeClass: 'border-red-500/30 bg-red-500/15 text-red-700 dark:text-red-300',
    icon: AlertTriangle,
  },
  warning: {
    label: 'Warning',
    badgeClass: 'border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300',
    icon: Info,
  },
  hint: {
    label: 'Hint',
    badgeClass: 'border-border bg-muted text-muted-foreground',
    icon: Info,
  },
}

export interface ContinuityPanelProps {
  bookId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * The Continuity panel (docs/06 Phase 4 task FE-4) — the UI over Continuity Checker v2
 * (deterministic rules always; AI/semantic checks only when opted in and never run on this
 * build machine per CLAUDE.md). A Dialog rather than a new panel primitive, reusing FE-1's
 * `useContinuityFlags`/`useRunContinuity`/`useUpdateFlag` hooks — no backend changes here.
 *
 * DATA-SENSITIVE NOTE: Dismiss/Resolve/Reopen only ever PATCH a flag's own `status` — they
 * never touch the Scene, Codex entry, or any other row a flag references.
 */
export function ContinuityPanel({ bookId, open, onOpenChange }: ContinuityPanelProps) {
  const [includeAi, setIncludeAi] = useState(false)
  const [showResolved, setShowResolved] = useState(false)
  // Local-only "has a check run happened yet" flag — the flags list itself can't tell us
  // this: an empty array means either "never checked" or "checked and clean". We treat any
  // already-persisted flag as evidence a previous check happened, and flip this true the
  // moment a check completes in this session.
  const [hasChecked, setHasChecked] = useState(false)

  const { data: flags, isLoading: flagsLoading } = useContinuityFlags(bookId)
  const { data: canvas } = useCanvas(bookId)
  const runContinuity = useRunContinuity(bookId)
  const updateFlag = useUpdateFlag(bookId)

  const sceneTitleById = useMemo(() => {
    const map = new Map<string, string>()
    for (const node of canvas?.nodes ?? []) map.set(node.scene_id, node.title)
    return map
  }, [canvas])

  const everChecked = hasChecked || (flags?.length ?? 0) > 0

  const visibleFlags = useMemo(() => {
    const list = flags ?? []
    return showResolved ? list : list.filter((flag) => flag.status === 'open')
  }, [flags, showResolved])

  const grouped = useMemo(() => {
    const groups: Record<ContinuitySeverity, ContinuityFlag[]> = { critical: [], warning: [], hint: [] }
    for (const flag of visibleFlags) groups[flag.severity].push(flag)
    return groups
  }, [visibleFlags])

  function handleRun() {
    runContinuity.mutate({ includeAi }, { onSuccess: () => setHasChecked(true) })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="size-5 text-primary" />
            Continuity
          </DialogTitle>
          <DialogDescription>
            Deterministic checks (character/location/timeline consistency) run instantly.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-3">
          <div className="flex items-start gap-2">
            <Switch
              id="continuity-include-ai"
              checked={includeAi}
              onCheckedChange={setIncludeAi}
              disabled={runContinuity.isPending}
            />
            <div className="flex flex-col">
              <Label htmlFor="continuity-include-ai" className="text-xs font-medium">
                Include AI (semantic) checks
              </Label>
              <span className="text-[11px] text-muted-foreground">
                AI checks need a local model (configured on your writing machine).
              </span>
            </div>
          </div>
          <Button size="sm" onClick={handleRun} disabled={runContinuity.isPending} className="gap-1.5">
            {runContinuity.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Sparkles className="size-3.5" />
            )}
            {runContinuity.isPending ? 'Checking…' : 'Check continuity'}
          </Button>
        </div>

        <div className="flex items-center justify-between gap-2 py-2">
          <span className="text-xs text-muted-foreground">
            {visibleFlags.length} {visibleFlags.length === 1 ? 'flag' : 'flags'} shown
          </span>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Switch size="sm" checked={showResolved} onCheckedChange={setShowResolved} />
            Show dismissed/resolved
          </label>
        </div>

        <ScrollArea className="min-h-0 flex-1 pr-3">
          <div className="flex flex-col gap-4 pb-1">
            {flagsLoading ? (
              <ContinuitySkeleton />
            ) : !everChecked ? (
              <EmptyState message="Run a check to find continuity issues." />
            ) : visibleFlags.length === 0 ? (
              <EmptyState message="No continuity issues found." success />
            ) : (
              SEVERITY_ORDER.map((severity) =>
                grouped[severity].length > 0 ? (
                  <section key={severity} className="flex flex-col gap-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {SEVERITY_META[severity].label} ({grouped[severity].length})
                    </h3>
                    <div className="flex flex-col gap-2">
                      {grouped[severity].map((flag) => (
                        <FlagCard
                          key={flag.id}
                          flag={flag}
                          sceneTitle={flag.scene_id ? sceneTitleById.get(flag.scene_id) : undefined}
                          onStatusChange={(status) => updateFlag.mutate({ id: flag.id, status })}
                          pending={updateFlag.isPending}
                        />
                      ))}
                    </div>
                  </section>
                ) : null,
              )
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

function FlagCard({
  flag,
  sceneTitle,
  onStatusChange,
  pending,
}: {
  flag: ContinuityFlag
  sceneTitle: string | undefined
  onStatusChange: (status: ContinuityStatus) => void
  pending: boolean
}) {
  const meta = SEVERITY_META[flag.severity]
  const isOpen = flag.status === 'open'

  return (
    <div className={cn('flex flex-col gap-2 rounded-xl border border-border p-3', !isOpen && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className={cn('border', meta.badgeClass)}>
          {meta.label}
        </Badge>
        <Badge variant="secondary" className="gap-1">
          {flag.source === 'ai' ? <Sparkles className="size-3" /> : <ShieldCheck className="size-3" />}
          {flag.source === 'ai' ? 'AI' : flag.source === 'manual' ? 'Manual' : 'SQL'}
        </Badge>
        {flag.flag_type && <Badge variant="outline">{flag.flag_type}</Badge>}
        {!isOpen && (
          <Badge variant="outline" className="capitalize text-muted-foreground">
            {flag.status}
          </Badge>
        )}
      </div>

      {sceneTitle && (
        // TODO(Phase 4 follow-up): no cross-tab selection/store exists yet to focus the
        // Canvas/Outline on this scene from here (see src/stores/canvas-actions.ts — it
        // only bridges "add node", not selection). Surfacing the scene title only for now
        // rather than building new cross-component plumbing for this task.
        <p className="text-xs font-medium text-foreground">Scene: {sceneTitle}</p>
      )}

      <p className="text-sm leading-relaxed text-foreground/90">{flag.description}</p>

      <div className="flex flex-wrap items-center gap-2">
        {isOpen ? (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onStatusChange('resolved')}
              disabled={pending}
              className="gap-1"
            >
              <Check className="size-3.5" />
              Resolve
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onStatusChange('dismissed')}
              disabled={pending}
              className="gap-1"
            >
              <X className="size-3.5" />
              Dismiss
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onStatusChange('open')}
            disabled={pending}
            className="gap-1"
          >
            <RotateCcw className="size-3.5" />
            Reopen
          </Button>
        )}
      </div>
    </div>
  )
}

function EmptyState({ message, success = false }: { message: string; success?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
      {success ? (
        <CheckCircle2 className="size-6 text-emerald-600 dark:text-emerald-400" />
      ) : (
        <ShieldCheck className="size-6 text-muted-foreground" />
      )}
      <p>{message}</p>
    </div>
  )
}

function ContinuitySkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-16 w-full rounded-xl" />
      ))}
    </div>
  )
}

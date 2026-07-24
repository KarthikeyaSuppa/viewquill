import { useEffect, useMemo, useState } from 'react'
import { CalendarClock, ListTree, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useCanvas } from '@/queries/canvas'
import { useOutline, useStructureTemplates } from '@/queries/outline'
import type { Book } from '@/queries/books'
import { BeatBoard, type BeatLane, type OutlineScene } from '@/components/outline/beat-board'
import { TimelineView } from '@/components/outline/timeline-view'
import { ContinuityPanel } from '@/components/outline/continuity-panel'

type OutlineView = 'outline' | 'timeline'

/**
 * The Outline tab (docs/06 Phase 4 tasks FE-2/FE-3): a structure-template picker + an
 * Outline/Timeline view toggle, backing onto the beat-board for the Outline view and
 * `TimelineView` for the Timeline view. Both views share the same joined scene list built
 * from `useCanvas` below.
 */
export function OutlinePanel({ bookId, book }: { bookId: string; book: Book | undefined }) {
  const [view, setView] = useState<OutlineView>('outline')
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const [continuityOpen, setContinuityOpen] = useState(false)

  const { data: templates, isLoading: templatesLoading } = useStructureTemplates(book?.book_type)
  const { data: canvas, isLoading: canvasLoading } = useCanvas(bookId)
  const { data: outlineRows, isLoading: outlineLoading } = useOutline(bookId)

  // Default to the first applicable template once templates load (docs/06 Phase 4 FE-2 —
  // the backend always includes "Freeform" as a catch-all, so this is never empty).
  useEffect(() => {
    if (selectedTemplateId || !templates || templates.length === 0) return
    setSelectedTemplateId(templates[0].id)
  }, [templates, selectedTemplateId])

  const selectedTemplate = templates?.find((template) => template.id === selectedTemplateId) ?? null

  const beats: BeatLane[] = useMemo(
    () =>
      (selectedTemplate?.beats ?? [])
        .slice()
        .sort((a, b) => a.order_index - b.order_index)
        .map((beat) => ({ name: beat.name, description: beat.description })),
    [selectedTemplate],
  )

  const scenes: OutlineScene[] = useMemo(
    () =>
      (canvas?.nodes ?? []).map((node) => ({
        id: node.scene_id,
        title: node.title,
        nodeType: node.node_type,
      })),
    [canvas],
  )

  const isLoading = templatesLoading || canvasLoading || outlineLoading

  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Select
          value={selectedTemplateId ?? undefined}
          onValueChange={setSelectedTemplateId}
          disabled={!templates || templates.length === 0}
        >
          <SelectTrigger size="sm" className="w-52" aria-label="Structure template">
            <SelectValue placeholder="Structure" />
          </SelectTrigger>
          <SelectContent>
            {(templates ?? []).map((template) => (
              <SelectItem key={template.id} value={template.id}>
                {template.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div
          className="glass glass-edge flex items-center gap-1 rounded-full p-1"
          role="tablist"
          aria-label="Outline or Timeline view"
        >
          <Button
            type="button"
            size="sm"
            variant={view === 'outline' ? 'secondary' : 'ghost'}
            className="rounded-full"
            role="tab"
            aria-selected={view === 'outline'}
            onClick={() => setView('outline')}
          >
            <ListTree className="size-4" />
            Outline
          </Button>
          <Button
            type="button"
            size="sm"
            variant={view === 'timeline' ? 'secondary' : 'ghost'}
            className="rounded-full"
            role="tab"
            aria-selected={view === 'timeline'}
            onClick={() => setView('timeline')}
          >
            <CalendarClock className="size-4" />
            Timeline
          </Button>
        </div>

        <Button type="button" size="sm" variant="outline" className="gap-1.5" onClick={() => setContinuityOpen(true)}>
          <ShieldCheck className="size-4" />
          Check continuity
        </Button>
      </div>

      <ContinuityPanel bookId={bookId} open={continuityOpen} onOpenChange={setContinuityOpen} />

      {view === 'timeline' ? (
        <TimelineView bookId={bookId} scenes={scenes} scenesLoading={canvasLoading} />
      ) : isLoading ? (
        <OutlineSkeleton />
      ) : (
        <BeatBoard bookId={bookId} beats={beats} scenes={scenes} orderRows={outlineRows ?? []} />
      )}
    </div>
  )
}

function OutlineSkeleton() {
  return (
    <div className="flex gap-3 overflow-x-auto pb-2" aria-hidden>
      {[0, 1, 2].map((column) => (
        <div key={column} className="flex w-64 shrink-0 flex-col gap-2 rounded-2xl border border-border p-2.5">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ))}
    </div>
  )
}

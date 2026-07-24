import { useEffect, useState } from 'react'
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useReorderTimeline, useSetTimeline, useTimeline } from '@/queries/outline'
import type { BookSceneOrder } from '@/lib/api'
import type { OutlineScene } from '@/components/outline/beat-board'
import { cn } from '@/lib/utils'

interface TimelineRow {
  sceneId: string
  title: string
  label: string
}

/** Orders scene ids by (in_story_time_sort_key NULLS LAST, timeline_order_index NULLS
 * LAST, title) — mirrors `outline_service.list_timeline`'s SQL ordering, with `title` as
 * the final tiebreaker instead of raw row id (more meaningful for a fresh, un-ordered
 * timeline where every row's key/index/id would otherwise be arbitrary). */
function buildRows(scenes: OutlineScene[], timelineRows: BookSceneOrder[]): TimelineRow[] {
  const rowBySceneId = new Map(timelineRows.map((row) => [row.scene_id, row]))

  return scenes
    .map((scene) => ({ scene, row: rowBySceneId.get(scene.id) }))
    .sort((a, b) => {
      const aKey = a.row?.in_story_time_sort_key ?? null
      const bKey = b.row?.in_story_time_sort_key ?? null
      if (aKey !== null && bKey !== null && aKey !== bKey) return aKey - bKey
      if (aKey !== null && bKey === null) return -1
      if (aKey === null && bKey !== null) return 1

      const aIndex = a.row?.timeline_order_index ?? null
      const bIndex = b.row?.timeline_order_index ?? null
      if (aIndex !== null && bIndex !== null && aIndex !== bIndex) return aIndex - bIndex
      if (aIndex !== null && bIndex === null) return -1
      if (aIndex === null && bIndex !== null) return 1

      return a.scene.title.localeCompare(b.scene.title)
    })
    .map(({ scene, row }) => ({
      sceneId: scene.id,
      title: scene.title,
      label: row?.in_story_time_label ?? '',
    }))
}

/**
 * The Timeline view (docs/06 Phase 4 task FE-3): the same scene set as the Outline, ordered
 * by in-story time rather than reading order — a single sortable vertical list (dnd-kit
 * single-container sortable, simpler than `BeatBoard`'s multi-lane setup) with an inline
 * editable "in-story time" label per row.
 *
 * The server (`useTimeline`) is the source of truth; local `rows` state is reconciled back
 * into it whenever the underlying query data changes — the same pattern `BeatBoard` uses.
 */
export function TimelineView({
  bookId,
  scenes,
  scenesLoading = false,
}: {
  bookId: string
  scenes: OutlineScene[]
  /** True while the underlying scene list (canvas nodes) is still loading — kept separate
   * from this view's own `useTimeline` query so the skeleton shows for either cause rather
   * than briefly flashing the empty state before scenes arrive. */
  scenesLoading?: boolean
}) {
  const { data: timelineRows, isLoading: timelineLoading } = useTimeline(bookId)
  const isLoading = scenesLoading || timelineLoading
  const reorderTimeline = useReorderTimeline(bookId)
  const setTimeline = useSetTimeline(bookId)

  const [rows, setRows] = useState<TimelineRow[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)

  useEffect(() => {
    setRows(buildRows(scenes, timelineRows ?? []))
  }, [scenes, timelineRows])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id))
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    setActiveId(null)
    if (!over || active.id === over.id) return

    const oldIndex = rows.findIndex((row) => row.sceneId === active.id)
    const newIndex = rows.findIndex((row) => row.sceneId === over.id)
    if (oldIndex === -1 || newIndex === -1) return

    const reordered = arrayMove(rows, oldIndex, newIndex)
    setRows(reordered)
    reorderTimeline.mutate(reordered.map((row) => row.sceneId))
  }

  function handleLabelChange(sceneId: string, label: string) {
    setRows((prev) => prev.map((row) => (row.sceneId === sceneId ? { ...row, label } : row)))
  }

  function handleLabelCommit(sceneId: string, label: string) {
    setTimeline.mutate({ sceneId, in_story_time_label: label.trim() === '' ? null : label })
  }

  if (isLoading) {
    return <TimelineSkeleton />
  }

  if (scenes.length === 0) {
    return (
      <div className="glass glass-edge flex min-h-[240px] items-center justify-center rounded-2xl px-6 text-center text-sm text-muted-foreground">
        Add scenes on the Canvas first — they’ll show up here to arrange along your story’s
        timeline.
      </div>
    )
  }

  const activeRow = activeId ? (rows.find((row) => row.sceneId === activeId) ?? null) : null

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveId(null)}
    >
      <div
        className="glass glass-edge flex max-h-[calc(100vh-20rem)] flex-col gap-2 overflow-y-auto rounded-2xl p-3"
        role="list"
        aria-label="Scenes ordered by in-story time"
      >
        <SortableContext items={rows.map((row) => row.sceneId)} strategy={verticalListSortingStrategy}>
          {rows.map((row, index) => (
            <SortableTimelineRow
              key={row.sceneId}
              row={row}
              isLast={index === rows.length - 1}
              onLabelChange={handleLabelChange}
              onLabelCommit={handleLabelCommit}
            />
          ))}
        </SortableContext>
      </div>
      <DragOverlay>{activeRow ? <TimelineRowPreview row={activeRow} /> : null}</DragOverlay>
    </DndContext>
  )
}

function SortableTimelineRow({
  row,
  isLast,
  onLabelChange,
  onLabelCommit,
}: {
  row: TimelineRow
  isLast: boolean
  onLabelChange: (sceneId: string, label: string) => void
  onLabelCommit: (sceneId: string, label: string) => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: row.sceneId,
  })

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className="relative flex gap-3"
      role="listitem"
    >
      <div className="flex flex-col items-center">
        <span className="mt-3 size-2.5 shrink-0 rounded-full bg-primary" aria-hidden />
        {!isLast && <span className="w-px flex-1 bg-border" aria-hidden />}
      </div>

      <div
        className={cn(
          'mb-2 flex flex-1 items-center gap-2 rounded-lg border border-border bg-card p-2.5 text-sm',
          isDragging && 'opacity-40',
        )}
      >
        <button
          type="button"
          className="shrink-0 cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
          aria-label={`Drag “${row.title}” to reorder it in the timeline`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-3.5" />
        </button>
        <span className="min-w-0 flex-1 truncate font-medium">{row.title}</span>
        <Input
          value={row.label}
          onChange={(event) => onLabelChange(row.sceneId, event.target.value)}
          onBlur={(event) => onLabelCommit(row.sceneId, event.target.value)}
          placeholder="e.g. Day 1 morning, 10 years earlier"
          aria-label={`In-story time for “${row.title}”`}
          className="h-8 w-56 shrink-0 text-sm"
        />
      </div>
    </div>
  )
}

/** Plain (non-sortable) row rendered inside `DragOverlay` — mirrors `BeatBoard`'s
 * `SceneCardPreview` idiom. */
function TimelineRowPreview({ row }: { row: TimelineRow }) {
  return (
    <div className="glass glass-edge ml-5 flex items-center gap-2 rounded-lg p-2.5 text-sm shadow-lg">
      <GripVertical className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1 truncate font-medium">{row.title}</span>
      {row.label && <span className="shrink-0 truncate text-xs text-muted-foreground">{row.label}</span>}
    </div>
  )
}

function TimelineSkeleton() {
  return (
    <div className="glass glass-edge flex flex-col gap-2 rounded-2xl p-3" aria-hidden>
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-2.5 shrink-0 rounded-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ))}
    </div>
  )
}

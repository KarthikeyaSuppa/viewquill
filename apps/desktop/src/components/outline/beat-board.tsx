import { useEffect, useMemo, useState } from 'react'
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
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
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useAssignScene, useReorderOutline } from '@/queries/outline'
import type { BookSceneOrder, NodeType } from '@/lib/api'
import { cn } from '@/lib/utils'

/** Sentinel lane id for scenes with no `structure_beat` — kept distinct from any real beat
 * name (even a template that happened to name a beat "Unassigned") since it's never sent
 * to the backend directly as a beat value (null is sent instead — see `handleDragEnd`). */
export const UNASSIGNED_LANE = '__unassigned__'

export interface BeatLane {
  name: string
  description: string
}

export interface OutlineScene {
  id: string
  title: string
  nodeType: NodeType
}

interface Lane {
  id: string
  name: string
  description: string | null
}

/** Cycled per-lane accents built on the existing chart-1..5 tokens (docs/10 idiom). Written
 * out as literal class names (not template-built) so Tailwind's scanner picks them all up. */
const LANE_COLORS = [
  { text: 'text-chart-1', bar: 'bg-chart-1', soft: 'bg-chart-1/10', ring: 'border-chart-1/50' },
  { text: 'text-chart-2', bar: 'bg-chart-2', soft: 'bg-chart-2/10', ring: 'border-chart-2/50' },
  { text: 'text-chart-3', bar: 'bg-chart-3', soft: 'bg-chart-3/10', ring: 'border-chart-3/50' },
  { text: 'text-chart-4', bar: 'bg-chart-4', soft: 'bg-chart-4/10', ring: 'border-chart-4/50' },
  { text: 'text-chart-5', bar: 'bg-chart-5', soft: 'bg-chart-5/10', ring: 'border-chart-5/50' },
]

const UNASSIGNED_COLOR = {
  text: 'text-muted-foreground',
  bar: 'bg-muted-foreground/50',
  soft: 'bg-muted/50',
  ring: 'border-border',
}

function buildLanes(beats: BeatLane[]): Lane[] {
  return [
    { id: UNASSIGNED_LANE, name: 'Unassigned', description: 'Not yet placed on the structure' },
    ...beats.map((beat) => ({ id: beat.name, name: beat.name, description: beat.description })),
  ]
}

/** Groups scene ids into lanes from the current outline rows, ordered by
 * `outline_order_index` (nulls last, stable) within each lane.
 *
 * A scene whose stored `structure_beat` doesn't match any lane currently on screen (e.g.
 * the structure-template selector was just switched to one without that beat) falls back
 * to Unassigned for DISPLAY ONLY — its stored beat is never touched by this, only by an
 * actual drag. */
function groupIntoLanes(
  lanes: Lane[],
  scenes: OutlineScene[],
  orderRows: BookSceneOrder[],
): Record<string, string[]> {
  const rowBySceneId = new Map(orderRows.map((row) => [row.scene_id, row]))
  const laneIds = new Set(lanes.map((lane) => lane.id))
  const groups: Record<string, string[]> = {}
  for (const lane of lanes) groups[lane.id] = []

  const withMeta = scenes.map((scene, index) => {
    const row = rowBySceneId.get(scene.id)
    const beat = row?.structure_beat
    const laneId = beat && laneIds.has(beat) ? beat : UNASSIGNED_LANE
    return { scene, laneId, orderIndex: row?.outline_order_index ?? null, fallbackIndex: index }
  })

  for (const laneId of laneIds) {
    const inLane = withMeta.filter((item) => item.laneId === laneId)
    inLane.sort((a, b) => {
      if (a.orderIndex !== null && b.orderIndex !== null) return a.orderIndex - b.orderIndex
      if (a.orderIndex !== null) return -1
      if (b.orderIndex !== null) return 1
      return a.fallbackIndex - b.fallbackIndex
    })
    groups[laneId] = inLane.map((item) => item.scene.id)
  }
  return groups
}

/**
 * The Outline beat-board (docs/06 Phase 4 task FE-2): one droppable lane per structure
 * beat (plus a leading "Unassigned" lane), scene cards drag/reorder within and across
 * lanes via dnd-kit's standard multi-container sortable pattern.
 *
 * The server (canvas scenes + outline rows) is the source of truth; local `laneState` is
 * reconciled back into it whenever the underlying query data changes — the same pattern
 * `CanvasPanel` uses for node/edge state — never the other way around.
 */
export function BeatBoard({
  bookId,
  beats,
  scenes,
  orderRows,
}: {
  bookId: string
  beats: BeatLane[]
  scenes: OutlineScene[]
  orderRows: BookSceneOrder[]
}) {
  const lanes = useMemo(() => buildLanes(beats), [beats])
  const sceneById = useMemo(() => new Map(scenes.map((scene) => [scene.id, scene])), [scenes])
  const assignScene = useAssignScene(bookId)
  const reorderOutline = useReorderOutline(bookId)

  const [laneState, setLaneState] = useState<Record<string, string[]>>({})
  const [activeId, setActiveId] = useState<string | null>(null)

  useEffect(() => {
    setLaneState(groupIntoLanes(lanes, scenes, orderRows))
  }, [lanes, scenes, orderRows])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function findLaneOf(sceneId: string): string | null {
    for (const lane of lanes) {
      if (laneState[lane.id]?.includes(sceneId)) return lane.id
    }
    return null
  }

  function resolveDestLane(overId: string): string | null {
    if (lanes.some((lane) => lane.id === overId)) return overId
    return findLaneOf(overId)
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id))
  }

  // Live cross-lane move while dragging, so a card visibly follows the pointer into
  // whichever lane it's hovering over (dnd-kit's standard multi-container pattern) — not
  // persisted yet, that happens in `handleDragEnd`.
  function handleDragOver(event: DragOverEvent) {
    const { active, over } = event
    if (!over) return
    const activeSceneId = String(active.id)
    const overId = String(over.id)
    const sourceLane = findLaneOf(activeSceneId)
    const destLane = resolveDestLane(overId)
    if (!sourceLane || !destLane || sourceLane === destLane) return

    setLaneState((prev) => {
      const sourceItems = (prev[sourceLane] ?? []).filter((id) => id !== activeSceneId)
      const destItems = [...(prev[destLane] ?? [])]
      const overIndex = destItems.indexOf(overId)
      destItems.splice(overIndex >= 0 ? overIndex : destItems.length, 0, activeSceneId)
      return { ...prev, [sourceLane]: sourceItems, [destLane]: destItems }
    })
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    setActiveId(null)
    if (!over) return
    const activeSceneId = String(active.id)
    const overId = String(over.id)
    const sourceLane = findLaneOf(activeSceneId)
    const destLane = resolveDestLane(overId)
    if (!sourceLane || !destLane) return

    let nextState = laneState
    if (sourceLane === destLane) {
      const items = laneState[destLane] ?? []
      const oldIndex = items.indexOf(activeSceneId)
      const newIndex = items.indexOf(overId)
      if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) return
      nextState = { ...laneState, [destLane]: arrayMove(items, oldIndex, newIndex) }
      setLaneState(nextState)
    }
    // Cross-lane moves were already applied to `laneState` live in `handleDragOver` —
    // `nextState` (== `laneState`) already reflects the drop.

    if (sourceLane !== destLane) {
      assignScene.mutate({
        sceneId: activeSceneId,
        structure_beat: destLane === UNASSIGNED_LANE ? null : destLane,
      })
    }

    const orderedSceneIds = lanes.flatMap((lane) => nextState[lane.id] ?? [])
    reorderOutline.mutate(orderedSceneIds)
  }

  if (scenes.length === 0) {
    return (
      <div className="glass glass-edge flex min-h-[240px] items-center justify-center rounded-2xl px-6 text-center text-sm text-muted-foreground">
        Add scenes on the Canvas first — they’ll show up here to arrange into your story’s
        structure.
      </div>
    )
  }

  const activeScene = activeId ? (sceneById.get(activeId) ?? null) : null

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveId(null)}
    >
      <div className="flex gap-3 overflow-x-auto pb-2">
        {lanes.map((lane, index) => (
          <BeatLaneColumn
            key={lane.id}
            lane={lane}
            color={lane.id === UNASSIGNED_LANE ? UNASSIGNED_COLOR : LANE_COLORS[index % LANE_COLORS.length]}
            sceneIds={laneState[lane.id] ?? []}
            sceneById={sceneById}
          />
        ))}
      </div>
      <DragOverlay>{activeScene ? <SceneCardPreview scene={activeScene} /> : null}</DragOverlay>
    </DndContext>
  )
}

function BeatLaneColumn({
  lane,
  color,
  sceneIds,
  sceneById,
}: {
  lane: Lane
  color: (typeof LANE_COLORS)[number]
  sceneIds: string[]
  sceneById: Map<string, OutlineScene>
}) {
  const { setNodeRef, isOver } = useDroppable({ id: lane.id })
  const count = sceneIds.length

  return (
    <div
      className="glass glass-edge flex w-64 shrink-0 flex-col gap-2 rounded-2xl p-2.5"
      role="group"
      aria-label={`${lane.name} lane, ${count} scene${count === 1 ? '' : 's'}`}
    >
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className={cn('size-2 shrink-0 rounded-full', color.bar)} aria-hidden />
          {lane.description ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="cursor-help truncate text-sm font-semibold">{lane.name}</span>
              </TooltipTrigger>
              <TooltipContent>{lane.description}</TooltipContent>
            </Tooltip>
          ) : (
            <span className="truncate text-sm font-semibold">{lane.name}</span>
          )}
        </div>
        <Badge variant="secondary" className={cn('shrink-0', color.text)}>
          {count}
        </Badge>
      </div>

      <SortableContext items={sceneIds} strategy={verticalListSortingStrategy}>
        <div
          ref={setNodeRef}
          className={cn(
            'flex min-h-24 flex-col gap-2 rounded-xl p-1.5 transition-colors',
            color.soft,
            isOver && `ring-2 ring-inset ${color.ring}`,
          )}
        >
          {sceneIds.map((sceneId) => {
            const scene = sceneById.get(sceneId)
            return scene ? <SortableSceneCard key={sceneId} scene={scene} /> : null
          })}
          {count === 0 && (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">Drop scenes here</p>
          )}
        </div>
      </SortableContext>
    </div>
  )
}

function SortableSceneCard({ scene }: { scene: OutlineScene }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: scene.id,
  })

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        'flex items-start gap-1.5 rounded-lg border border-border bg-card p-2 text-sm',
        isDragging && 'opacity-40',
      )}
    >
      <button
        type="button"
        className="mt-0.5 shrink-0 cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
        aria-label={`Drag “${scene.title}” to reorder or move to another beat`}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-3.5" />
      </button>
      <span className="min-w-0 flex-1 truncate">{scene.title}</span>
    </div>
  )
}

/** Plain (non-sortable) card rendered inside `DragOverlay` — the lifted copy that follows
 * the pointer while the real card's slot is held open by dnd-kit. */
function SceneCardPreview({ scene }: { scene: OutlineScene }) {
  return (
    <div className="glass glass-edge flex items-start gap-1.5 rounded-lg p-2 text-sm shadow-lg">
      <GripVertical className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{scene.title}</span>
    </div>
  )
}

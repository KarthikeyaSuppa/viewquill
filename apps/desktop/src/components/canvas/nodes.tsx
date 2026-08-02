import { useState, type ComponentType, type CSSProperties, type MouseEvent } from 'react'
import { Handle, Position, type Node, type NodeProps, type NodeTypes } from '@xyflow/react'
import {
  Clapperboard,
  Copy,
  EllipsisVertical,
  History as HistoryIcon,
  Image,
  ImageOff,
  Lightbulb,
  MapPinned,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { isFirstConnectHint } from '@/lib/delight'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { ScreenplayNode } from '@/components/canvas/screenplay-node'
import { useCreateNode, useRemoveFromCanvas } from '@/queries/canvas'
import { useDeleteScene, useSceneRevisions, type SceneRevision } from '@/queries/screenplay'
import { showUndoToast, useRedoLastAction, useUndoLastAction } from '@/queries/undo'
import { imageThumbUrl, useEntityImages } from '@/queries/images'
import { Skeleton } from '@/components/ui/skeleton'
import { useCardStyleStore } from '@/stores/card-style'
import type { NodeType } from '@/lib/api'

/** Badge label for `SceneRevision.change_source` — falls back to the raw value verbatim for
 * anything unrecognized (the backend is free to add sources later without breaking this UI). */
const CHANGE_SOURCE_LABELS: Record<string, string> = {
  manual_edit: 'Manual edit',
  enhance_accept: 'Enhance accepted',
  ai_merge: 'AI merge',
  restore: 'Restored',
}

/** Same relative-time formatting as `formatGeneratedAt` in `src/components/draft/version-list.tsx`
 * (itself matching `formatRelative` in `src/routes/library-screen.tsx`) — hand-duplicated per
 * this codebase's existing convention of small per-file formatting helpers. */
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

/** One row in the History popover — read-only, no restore/rollback action (that needs its
 * own backend endpoint, out of scope here). */
function RevisionRow({ revision }: { revision: SceneRevision }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border/60 px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-semibold text-foreground">Rev {revision.revision_number}</span>
        <Badge variant="secondary" className="text-[10px]">
          {CHANGE_SOURCE_LABELS[revision.change_source] ?? revision.change_source}
        </Badge>
        <span className="text-[11px] text-muted-foreground">{formatRevisionTime(revision.created_at)}</span>
      </div>
      <p className="line-clamp-1 text-xs font-medium text-foreground">{revision.title}</p>
      {revision.description && (
        <p className="line-clamp-2 text-[11px] text-muted-foreground">{revision.description}</p>
      )}
    </div>
  )
}

/** The ⋯ menu's "History" popover content (PHASE11.md Workstream B) — a read-only list of
 * one Scene's revision snapshots, newest-first (server-sorted, per `useSceneRevisions`).
 * Not a `PopoverTrigger` itself — a Radix `Popover` can't nest its trigger inside a
 * `DropdownMenu` item and stay open once that menu closes on select, so `BaseNode` instead
 * controls an outer `Popover`'s `open` state directly (same controlled pattern as its
 * delete `AlertDialog` below) and anchors it to the ⋯ trigger; this component is just the
 * `PopoverContent` body. Only fetches once opened (`enabled` gates on the `open` flag it's
 * passed) so idle nodes on a large canvas don't all fire a revisions request on mount. */
function HistoryPopoverContent({ sceneId, open }: { sceneId: string; open: boolean }) {
  const { data: revisions, isLoading } = useSceneRevisions(open ? sceneId : undefined)

  return (
    <PopoverContent
      align="end"
      className="max-h-80 w-80 overflow-y-auto"
      onClick={(event) => event.stopPropagation()}
    >
      <p className="mb-2 text-xs font-semibold text-muted-foreground">Edit history</p>
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !revisions || revisions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No edit history yet.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {revisions.map((revision) => (
            <RevisionRow key={revision.id} revision={revision} />
          ))}
        </div>
      )}
    </PopoverContent>
  )
}

/** Shared per-node payload — canonical Scene fields plus this canvas's link id. */
export interface CanvasNodeData extends Record<string, unknown> {
  linkId: string
  sceneId: string
  bookId: string
  nodeType: NodeType
  title: string
  description: string | null
  status: string | null
}

/** `'screenplay'` is a display-only variant of `'scene'` used on script-type Books
 * (docs/06 Phase 2 task G4) — the canonical node_type on the server is still "scene". */
export type SceneFlowNode = Node<CanvasNodeData, 'scene' | 'plot_point' | 'thought' | 'screenplay'>

/** `accentClass` looks like `bg-[oklch(0.54_0.21_277)]` (Tailwind's arbitrary-value
 * underscore-for-space convention) — strips the `bg-[...]` wrapper and restores real
 * spaces so the same node-type color `BaseNodeConfig` already computes for the accent
 * strip can be reused as a plain CSS color value for the handle's `--handle-accent`
 * custom property below, instead of inventing a second color per node type. */
function accentColorFromClass(accentClass: string): string {
  return accentClass.replace(/^bg-\[(.+)\]$/, '$1').replace(/_/g, ' ')
}

/** Handle ids match `EdgeCreate.source_handle`/`target_handle` — kept stable across renders.
 * At rest, handles are a low-opacity but always-visible dot (bigger than xyflow's own
 * hover-only default) so they read as "grabbable" without hovering first; on hover/focus
 * they grow further and swap fill to this node type's own accent color via the
 * `--handle-accent` custom property (`.node-handle-accent` in `index.css`, same pattern as
 * `image-card.tsx`'s `--image-shadow-src`) since that color varies per node type and can't
 * be expressed as a static Tailwind class here. Purely a CSS hover transition, same
 * ungated precedent as this file's own `hover:scale-125` on the thumbnail strip below —
 * not gated behind `useDelight().motionOk`. */
function NodeHandles({ accentClass }: { accentClass: string }) {
  const style = { '--handle-accent': accentColorFromClass(accentClass) } as CSSProperties
  const className =
    'node-handle-accent !size-3.5 !border-2 !bg-background !opacity-70 transition-all hover:!size-5 hover:!opacity-100 focus-visible:!size-5 focus-visible:!opacity-100'

  // One-time onboarding hint (see `lib/delight.ts`'s `isFirstConnectHint`, mirrors
  // `isFirstNodeMilestone`'s check-then-set-in-one-call localStorage pattern): only the
  // very first `NodeHandles` to mount across this profile's lifetime gets `true` back, so
  // only that one node's two `source` handles (bottom/right — the ones a user actually
  // drags FROM to start a connection) get wrapped in a hint `Tooltip`. Every other node,
  // this session or any future one, renders plain `Handle`s exactly as task 3 left them.
  const [showConnectHint] = useState(() => isFirstConnectHint())

  return (
    <>
      <Handle id="top" type="target" position={Position.Top} className={className} style={style} />
      <Handle id="left" type="target" position={Position.Left} className={className} style={style} />
      {showConnectHint ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Handle id="bottom" type="source" position={Position.Bottom} className={className} style={style} />
          </TooltipTrigger>
          <TooltipContent side="bottom">Drag to connect to another node</TooltipContent>
        </Tooltip>
      ) : (
        <Handle id="bottom" type="source" position={Position.Bottom} className={className} style={style} />
      )}
      {showConnectHint ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <Handle id="right" type="source" position={Position.Right} className={className} style={style} />
          </TooltipTrigger>
          <TooltipContent side="right">Drag to connect to another node</TooltipContent>
        </Tooltip>
      ) : (
        <Handle id="right" type="source" position={Position.Right} className={className} style={style} />
      )}
    </>
  )
}

/** Where a node type's image-area aspect ratio comes from:
 * - `'scene-preference'`: read the user's global Canvas-tab rectangle/square toggle
 *   (`useCardStyleStore`) — today's Scene behavior, preserved exactly.
 * - `{ fixed: string }`: a Tailwind aspect class baked into the node type itself,
 *   independent of that toggle (Plot Point/Thought — shape now signals type). */
type AspectSource = 'scene-preference' | { fixed: string }

interface BaseNodeConfig {
  accentClass: string
  icon: ComponentType<{ className?: string }>
  label: string
  aspectSource: AspectSource
  /** Outer card corner rounding — defaults to the shared `rounded-2xl` every type used
   * before this field existed; only Thought overrides it. */
  cardRadiusClass?: string
}

/** The node-card redesign (docs/10 node canvas redesign, task FE-B): a main image area
 * (the scene's first attached image per the backend's order — explicit `order_index` first,
 * else newest — else the original dashed-border placeholder), a 3-button action row below the
 * card (Enhance/Duplicate/⋯), and — beside the card — a vertical strip of up to 4 more
 * attached-image thumbnails. Only Duplicate and the ⋯ trigger stop click propagation;
 * everything else (header, image, title, description, thumbnail strip) lets the click
 * bubble up to xyflow's `onNodeClick`, which is what opens the `NodeEditor` drawer. */
function BaseNode(
  { data, selected, positionAbsoluteX, positionAbsoluteY }: NodeProps<SceneFlowNode>,
  { accentClass, icon: Icon, label, aspectSource, cardRadiusClass = 'rounded-2xl' }: BaseNodeConfig,
) {
  // Called unconditionally (rules of hooks) regardless of `aspectSource` — its value only
  // feeds `aspectClass` below when a node type actually opts into following it.
  const cardStyle = useCardStyleStore((state) => state.cardStyle)
  const { data: images, isLoading: imagesLoading, isError: imagesError } = useEntityImages('scene', data.sceneId)
  const createNode = useCreateNode(data.bookId)
  const removeFromCanvas = useRemoveFromCanvas(data.bookId)
  const deleteScene = useDeleteScene()
  const undoLastAction = useUndoLastAction(data.bookId)
  const redoLastAction = useRedoLastAction(data.bookId)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  // `useEntityImages` hits `GET /entities/scene/{id}/images`, which the sidecar's
  // `entity_images_service.list_for_entity` orders by `order_index IS NULL, order_index ASC,
  // created_at DESC, id DESC` — explicitly-ordered images (via the reorder endpoint) come
  // first in that order, everything else falls back to recency. So the first item is simply
  // whatever the user (or, absent any ordering, recency) says is the cover; no bucket
  // heuristic needed. Falls back to the placeholder if nothing's attached.
  // NOTE: `images` is also `undefined` while loading or on a fetch error — neither case means
  // the entity actually has zero images, so callers must gate on `imagesLoading`/`imagesError`
  // rather than reading an empty `mainImage`/`thumbnails` as "confirmed no images".
  const mainImage = images?.[0] ?? null
  const thumbnails = (images ?? []).slice(0, 4)
  const aspectClass =
    aspectSource === 'scene-preference'
      ? cardStyle === 'square'
        ? 'aspect-square'
        : 'aspect-[16/10]'
      : aspectSource.fixed

  function handleDuplicate(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation()
    createNode.mutate({
      node_type: data.nodeType,
      title: `${data.title} (Copy)`,
      description: data.description,
      canvas_x: positionAbsoluteX + 40,
      canvas_y: positionAbsoluteY + 40,
    })
  }

  function handleMenuTriggerClick(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation()
  }

  return (
    <div className="flex items-start gap-2">
      <div className="flex flex-col gap-2">
        <div
          className={cn(
            'glass glass-edge relative w-64 overflow-hidden border-0 shadow-lg transition-shadow',
            cardRadiusClass,
            selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
          )}
        >
          <NodeHandles accentClass={accentClass} />
          <div className={cn('h-1.5 w-full', accentClass)} />
          <div className="flex flex-col gap-2 p-4">
            <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Icon className="size-3.5" />
              {label}
            </div>

            {imagesLoading ? (
              <Skeleton className={cn('w-full rounded-lg', aspectClass)} aria-hidden />
            ) : mainImage ? (
              <img
                src={imageThumbUrl(mainImage.id)}
                alt=""
                className={cn('w-full rounded-lg object-cover', aspectClass)}
              />
            ) : (
              // Distinguishable at a glance, not just on hover: a failed images fetch (`imagesError`)
              // swaps in `ImageOff` instead of the generic `Image` icon, so "query errored" reads
              // differently from a genuinely-empty state even before the `title` tooltip is seen.
              // See the NOTE on `mainImage` above for why this placeholder can mean either "none
              // attached" or "failed to load".
              <div
                className={cn(
                  'flex w-full items-center justify-center rounded-lg border border-dashed border-border text-muted-foreground',
                  aspectClass,
                )}
                title={imagesError ? 'Could not load attached images' : undefined}
                aria-hidden
              >
                {imagesError ? <ImageOff className="size-5" /> : <Image className="size-5" />}
              </div>
            )}

            <p className="line-clamp-1 text-sm font-semibold text-foreground">{data.title}</p>
            <p className="line-clamp-2 min-h-[2lh] text-xs text-muted-foreground">
              {data.description || 'No description yet.'}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between px-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-lg" className="rounded-full">
                <Sparkles className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Open to enhance</TooltipContent>
          </Tooltip>

          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-lg"
                  className="rounded-full"
                  aria-label="Duplicate"
                  onClick={handleDuplicate}
                  disabled={createNode.isPending}
                >
                  <Copy className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Duplicate</TooltipContent>
            </Tooltip>

            {/* Controlled `Popover` wraps the whole `DropdownMenu`, anchored to it via
                `PopoverAnchor` — a Radix `Popover` can't nest its trigger inside a
                `DropdownMenuItem` and stay open past the menu's own close-on-select, so
                "History" instead just flips `historyOpen` (mirrors `setDeleteOpen` below)
                and this outer `Popover` opens anchored to the same ⋯ button. */}
            <Popover open={historyOpen} onOpenChange={setHistoryOpen}>
              <PopoverAnchor asChild>
                <div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon-lg"
                        className="rounded-full"
                        aria-label="More actions"
                        onClick={handleMenuTriggerClick}
                      >
                        <EllipsisVertical className="size-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setHistoryOpen(true)}>
                        <HistoryIcon className="size-3.5" />
                        History
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onSelect={() => removeFromCanvas.mutate(data.sceneId)}
                        title="Only unlinks this scene from this canvas — it stays in the Library and on any other Book it's linked to."
                      >
                        Remove from canvas
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        variant="destructive"
                        onSelect={() => setDeleteOpen(true)}
                        title="Permanently deletes this scene everywhere it's used. This can be undone via Undo, but only briefly."
                      >
                        Delete permanently
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </PopoverAnchor>
              <HistoryPopoverContent sceneId={data.sceneId} open={historyOpen} />
            </Popover>
          </div>
        </div>
      </div>

      {thumbnails.length > 0 && (
        <div className="flex flex-col gap-1.5 pt-1">
          {thumbnails.map((image) => (
            <img
              key={image.id}
              src={imageThumbUrl(image.id)}
              alt=""
              // No `onClick`/`stopPropagation` here on purpose — same as the main image/title/
              // description above, this deliberately lets the click bubble up to xyflow's
              // `.react-flow__node` wrapper (`onSelectNodeHandler` in @xyflow/react), which is
              // what fires `onNodeClick` → `handleNodeClick` in `canvas-panel.tsx` and opens this
              // node's `NodeEditor` drawer — the same drawer a click anywhere else on the card
              // opens. Stopping propagation here (like `handleDuplicate`/the ⋯ trigger do) would
              // be wrong: those guard a *different* action from also triggering node-select; a
              // thumbnail click has no separate action of its own, so it should behave exactly
              // like clicking the card, including respecting a Shift-click's multi-select path.
              // `draggable={false}` avoids the browser's native image-drag gesture (which starts
              // on the same mousedown xyflow's own node-drag detection listens for) turning what
              // the user intends as a click into a spurious tiny drag.
              draggable={false}
              className="size-10 cursor-pointer rounded-md object-cover transition-transform hover:scale-125"
            />
          ))}
        </div>
      )}

      {/* Controlled — not nested inside the DropdownMenuItem — so the menu can close on
          "Delete permanently" (onSelect) while this dialog opens independently, mirroring
          `ImageCard`'s `DeleteAlert` pattern in `src/components/images/image-card.tsx`.
          Copy/structure matches `node-editor.tsx`'s "Delete scene permanently" confirmation
          verbatim per this task's brief. */}
      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this scene forever?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the scene — its title, description, and (for
              screenplay scenes) every element in it — everywhere it appears, including
              every other Book it's linked to. This can be undone via Undo, but only
              briefly — after that it's gone for good. If you only want to remove it from
              this canvas, use “Remove from canvas” instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteScene.isPending}
              onClick={(event: MouseEvent<HTMLButtonElement>) => {
                event.stopPropagation()
                deleteScene.mutate(data.sceneId, {
                  onSuccess: () => {
                    setDeleteOpen(false)
                    showUndoToast(
                      `“${data.title}” deleted permanently`,
                      () => undoLastAction.mutate(),
                      () => redoLastAction.mutate(),
                    )
                  },
                })
              }}
            >
              Delete permanently
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/** node_type="scene" — indigo, the default prose beat. Shape follows the user's global
 * Canvas-tab rectangle/square toggle (`useCardStyleStore`), exactly as before this task. */
export function SceneNode(props: NodeProps<SceneFlowNode>) {
  return BaseNode(props, {
    accentClass: 'bg-[oklch(0.54_0.21_277)]',
    icon: Clapperboard,
    label: 'Scene',
    aspectSource: 'scene-preference',
  })
}

/** node_type="plot_point" — amber, a structural beat/turn. Always a vertical rectangle
 * (taller than wide) regardless of the Scene shape toggle, so shape itself signals type. */
export function PlotPointNode(props: NodeProps<SceneFlowNode>) {
  return BaseNode(props, {
    accentClass: 'bg-[oklch(0.7_0.16_55)]',
    icon: MapPinned,
    label: 'Plot Point',
    aspectSource: { fixed: 'aspect-[3/4]' },
  })
}

/** node_type="thought" — cyan, a loose idea not yet a scene. Always square with rounder
 * corners than every other node type, regardless of the Scene shape toggle. */
export function ThoughtNode(props: NodeProps<SceneFlowNode>) {
  return BaseNode(props, {
    accentClass: 'bg-[oklch(0.6_0.13_195)]',
    icon: Lightbulb,
    label: 'Thought',
    aspectSource: { fixed: 'aspect-square' },
    cardRadiusClass: 'rounded-[2rem]',
  })
}

export const nodeTypes: NodeTypes = {
  scene: SceneNode,
  plot_point: PlotPointNode,
  thought: ThoughtNode,
  screenplay: ScreenplayNode,
}

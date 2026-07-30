import { useState, type ComponentType, type MouseEvent } from 'react'
import { Handle, Position, type Node, type NodeProps, type NodeTypes } from '@xyflow/react'
import {
  Clapperboard,
  Copy,
  EllipsisVertical,
  Image,
  Lightbulb,
  MapPinned,
  Sparkles,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
import { useDeleteScene } from '@/queries/screenplay'
import { imageThumbUrl, useEntityImages } from '@/queries/images'
import { Skeleton } from '@/components/ui/skeleton'
import { useCardStyleStore } from '@/stores/card-style'
import type { NodeType } from '@/lib/api'

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

/** Handle ids match `EdgeCreate.source_handle`/`target_handle` — kept stable across renders. */
function NodeHandles() {
  return (
    <>
      <Handle id="top" type="target" position={Position.Top} className="!size-2.5 !border-2 !bg-background" />
      <Handle id="left" type="target" position={Position.Left} className="!size-2.5 !border-2 !bg-background" />
      <Handle id="bottom" type="source" position={Position.Bottom} className="!size-2.5 !border-2 !bg-background" />
      <Handle id="right" type="source" position={Position.Right} className="!size-2.5 !border-2 !bg-background" />
    </>
  )
}

interface BaseNodeConfig {
  accentClass: string
  icon: ComponentType<{ className?: string }>
  label: string
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
  { accentClass, icon: Icon, label }: BaseNodeConfig,
) {
  const cardStyle = useCardStyleStore((state) => state.cardStyle)
  const { data: images, isLoading: imagesLoading, isError: imagesError } = useEntityImages('scene', data.sceneId)
  const createNode = useCreateNode(data.bookId)
  const removeFromCanvas = useRemoveFromCanvas(data.bookId)
  const deleteScene = useDeleteScene()
  const [deleteOpen, setDeleteOpen] = useState(false)

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
  const aspectClass = cardStyle === 'square' ? 'aspect-square' : 'aspect-[16/10]'

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
            'glass glass-edge relative w-64 overflow-hidden rounded-2xl border-0 shadow-lg transition-shadow',
            selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
          )}
        >
          <NodeHandles />
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
              // No distinct visual for the error case (small, scoped fix) — but it's deliberately
              // not conflated with a confirmed-empty state; see the NOTE on `mainImage` above for
              // why this placeholder can mean either "none attached" or "failed to load".
              <div
                className={cn(
                  'flex w-full items-center justify-center rounded-lg border border-dashed border-border text-muted-foreground',
                  aspectClass,
                )}
                title={imagesError ? 'Could not load attached images' : undefined}
                aria-hidden
              >
                <Image className="size-5" />
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
                <DropdownMenuItem onSelect={() => removeFromCanvas.mutate(data.sceneId)}>
                  Remove from canvas
                </DropdownMenuItem>
                <DropdownMenuItem variant="destructive" onSelect={() => setDeleteOpen(true)}>
                  Delete permanently
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
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
              className="size-10 rounded-md object-cover transition-transform hover:scale-125"
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
              every other Book it's linked to. This cannot be undone. If you only want to
              remove it from this canvas, use “Remove from canvas” instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteScene.isPending}
              onClick={(event: MouseEvent<HTMLButtonElement>) => {
                event.stopPropagation()
                deleteScene.mutate(data.sceneId, { onSuccess: () => setDeleteOpen(false) })
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

/** node_type="scene" — indigo, the default prose beat. */
export function SceneNode(props: NodeProps<SceneFlowNode>) {
  return BaseNode(props, { accentClass: 'bg-[oklch(0.54_0.21_277)]', icon: Clapperboard, label: 'Scene' })
}

/** node_type="plot_point" — amber, a structural beat/turn. */
export function PlotPointNode(props: NodeProps<SceneFlowNode>) {
  return BaseNode(props, { accentClass: 'bg-[oklch(0.7_0.16_55)]', icon: MapPinned, label: 'Plot Point' })
}

/** node_type="thought" — cyan, a loose idea not yet a scene. */
export function ThoughtNode(props: NodeProps<SceneFlowNode>) {
  return BaseNode(props, { accentClass: 'bg-[oklch(0.6_0.13_195)]', icon: Lightbulb, label: 'Thought' })
}

export const nodeTypes: NodeTypes = {
  scene: SceneNode,
  plot_point: PlotPointNode,
  thought: ThoughtNode,
  screenplay: ScreenplayNode,
}

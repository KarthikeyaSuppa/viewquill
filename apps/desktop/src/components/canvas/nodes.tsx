import type { ComponentType } from 'react'
import { Handle, Position, type Node, type NodeProps, type NodeTypes } from '@xyflow/react'
import { Clapperboard, Image, Lightbulb, MapPinned, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ScreenplayNode } from '@/components/canvas/screenplay-node'

/** Shared per-node payload — canonical Scene fields plus this canvas's link id. */
export interface CanvasNodeData extends Record<string, unknown> {
  linkId: string
  sceneId: string
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

function BaseNode({ data, selected }: NodeProps<SceneFlowNode>, { accentClass, icon: Icon, label }: BaseNodeConfig) {
  return (
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
        <p className="line-clamp-1 text-sm font-semibold text-foreground">{data.title}</p>
        <p className="line-clamp-2 min-h-[2lh] text-xs text-muted-foreground">
          {data.description || 'No description yet.'}
        </p>
        <div className="mt-1 flex items-center justify-between gap-2">
          <div
            className="flex size-8 items-center justify-center rounded-md border border-dashed border-border text-muted-foreground"
            aria-hidden
          >
            <Image className="size-3.5" />
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button variant="ghost" size="sm" disabled className="gap-1 text-xs">
                  <Sparkles className="size-3.5" />
                  Enhance
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>Enhance — coming next</TooltipContent>
          </Tooltip>
        </div>
      </div>
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

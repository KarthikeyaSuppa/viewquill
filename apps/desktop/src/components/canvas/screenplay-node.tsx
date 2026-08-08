import { Handle, Position, type NodeProps } from '@xyflow/react'
import { Clapperboard, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useElements } from '@/queries/screenplay'
import type { SceneFlowNode } from '@/components/canvas/nodes'

/** node_type="scene" on a script-type Book — same Handle layout as the prose nodes
 * (docs/06 Phase 2 task G4), but the body previews the scene's screenplay elements
 * (heading + element count) instead of free prose description. */
export function ScreenplayNode({ data, selected }: NodeProps<SceneFlowNode>) {
  const { data: elements } = useElements(data.sceneId)
  const heading = elements?.find((el) => el.element_type === 'scene_heading')
  const elementCount = elements?.length ?? 0

  return (
    <div
      className={cn(
        'glass glass-edge relative w-64 overflow-hidden rounded-2xl border-0 shadow-lg transition-shadow',
        selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
      )}
    >
      <Handle id="top" type="source" position={Position.Top} className="!size-2.5 !border-2 !bg-background" />
      <Handle id="left" type="source" position={Position.Left} className="!size-2.5 !border-2 !bg-background" />
      <Handle id="bottom" type="source" position={Position.Bottom} className="!size-2.5 !border-2 !bg-background" />
      <Handle id="right" type="source" position={Position.Right} className="!size-2.5 !border-2 !bg-background" />
      <div className="h-1.5 w-full bg-[oklch(0.6_0.19_25)]" />
      <div className="flex flex-col gap-2 p-4">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Clapperboard className="size-3.5" />
          Screenplay Scene
        </div>
        <p className="line-clamp-1 text-sm font-semibold text-foreground">{data.title}</p>
        <p className="line-clamp-1 min-h-[1lh] font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
          {heading?.text || 'No scene heading yet.'}
        </p>
        <p className="text-xs text-muted-foreground">
          {elementCount === 0
            ? 'No elements yet'
            : `${elementCount} element${elementCount === 1 ? '' : 's'}`}
        </p>
        <div className="mt-1 flex items-center justify-end">
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

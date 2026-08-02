import { BaseEdge, EdgeLabelRenderer, getBezierPath, type Edge, type EdgeProps } from '@xyflow/react'
import { useDelight } from '@/lib/delight'

/** Per-edge payload stashed on the xyflow `Edge.data` — mirrors `CanvasEdge.connection_type`/
 * `sequence_weight` (`src/lib/api.ts`), set from `canvas-panel.tsx`'s edge mapping. */
export interface InkEdgeData extends Record<string, unknown> {
  connectionType?: string | null
  /** Non-null marks this edge as a lineage/sequence step (backend rendering hint) rather
   * than an arbitrary free-form connection — see `CanvasEdge.sequence_weight`. */
  sequenceWeight?: number | null
}

export type InkFlowEdge = Edge<InkEdgeData>

/**
 * A quill-ink styled canvas edge (docs/10 §5 "delight base"): a static bezier stroke plus
 * a second dashed stroke that animates a flowing pulse along the path (an Animated-Beam
 * feel, done with a plain CSS `stroke-dashoffset` keyframe — see `.ink-edge-flow` in
 * index.css — no extra deps). The base stroke always renders; the animated pulse layer is
 * only mounted when `useDelight().motionOk` is true, so it disappears entirely at
 * delight_level 'calm' or under `prefers-reduced-motion` rather than just freezing in
 * place. This is chrome/canvas decoration only — never used on the manuscript surface.
 *
 * Edges tagged with a non-null `data.sequenceWeight` (backend `sequence_weight`, a rendering
 * hint for "this is a lineage/sequence step") render with a thicker stroke and the existing
 * `--chart-4` theme token (already the plot-point node accent — nothing new introduced) —
 * plus a closed arrowhead so the direction reads as directed lineage rather than a plain
 * undirected-looking connection; the arrowhead itself is set as `markerEnd` on the `Edge`
 * object in `canvas-panel.tsx`'s edge mapping (xyflow only accepts a marker *object* at that
 * level — by the time it reaches this component as the `markerEnd` prop it's already been
 * resolved to a marker-id string, so the object can't be built here). Plain edges (the
 * overwhelming majority today, since nothing writes `sequence_weight` yet) are completely
 * unaffected.
 */
export function InkEdge({
  id,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  style,
  markerEnd,
  markerStart,
  label,
  labelStyle,
  data,
}: EdgeProps<InkFlowEdge>) {
  const { motionOk } = useDelight()
  const isSequence = data?.sequenceWeight != null

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerStart={markerStart}
        markerEnd={markerEnd}
        style={{
          stroke: isSequence ? 'var(--chart-4)' : 'var(--muted-foreground)',
          strokeWidth: isSequence ? 2.5 : 1.75,
          opacity: isSequence ? 0.75 : 0.55,
          ...style,
        }}
      />
      {motionOk && (
        <path
          d={edgePath}
          fill="none"
          stroke="var(--primary)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeDasharray="6 10"
          className="ink-edge-flow"
          style={{ opacity: 0.7 }}
          aria-hidden="true"
        />
      )}
      {label && (
        <EdgeLabelRenderer>
          <div
            className="glass rounded-md px-1.5 py-0.5 text-[10px] font-medium text-foreground"
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'none',
              ...labelStyle,
            }}
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
}

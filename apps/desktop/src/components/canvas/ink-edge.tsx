import { BaseEdge, EdgeLabelRenderer, getBezierPath, type Edge, type EdgeProps } from '@xyflow/react'
import { useDelight } from '@/lib/delight'

/**
 * A quill-ink styled canvas edge (docs/10 §5 "delight base"): a static bezier stroke plus
 * a second dashed stroke that animates a flowing pulse along the path (an Animated-Beam
 * feel, done with a plain CSS `stroke-dashoffset` keyframe — see `.ink-edge-flow` in
 * index.css — no extra deps). The base stroke always renders; the animated pulse layer is
 * only mounted when `useDelight().motionOk` is true, so it disappears entirely at
 * delight_level 'calm' or under `prefers-reduced-motion` rather than just freezing in
 * place. This is chrome/canvas decoration only — never used on the manuscript surface.
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
}: EdgeProps<Edge>) {
  const { motionOk } = useDelight()

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
        style={{ stroke: 'var(--muted-foreground)', strokeWidth: 1.75, opacity: 0.55, ...style }}
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

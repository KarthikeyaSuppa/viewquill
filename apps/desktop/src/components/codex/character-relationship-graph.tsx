import { useMemo } from 'react'
import {
  Background,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type EdgeTypes,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
  type NodeTypes,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Users } from 'lucide-react'
import { InkEdge } from '@/components/canvas/ink-edge'
import { cn } from '@/lib/utils'
import type { CodexEntry, CodexRelationship } from '@/lib/api'

/** All edges reuse the Canvas tab's quill-ink styled edge (`components/canvas/ink-edge.tsx`)
 * so this second React Flow surface reads as the same visual language rather than inventing
 * a new one — its animated pulse layer is itself gated on `useDelight().motionOk`. */
const edgeTypes: EdgeTypes = { ink: InkEdge }

interface CharacterNodeData extends Record<string, unknown> {
  entry: CodexEntry
}

type CharacterFlowNode = Node<CharacterNodeData, 'character'>

/** A deliberately small custom node — just the character's name in a rounded glass card,
 * matching the app's card/glass conventions (`glass glass-edge`, same tokens as
 * `components/canvas/nodes.tsx`) without pulling in that node's image/action-row complexity,
 * which belongs to Scene nodes, not Codex characters. */
function CharacterNode({ data, selected }: NodeProps<CharacterFlowNode>) {
  return (
    <div
      className={cn(
        'glass glass-edge flex w-44 items-center gap-2 rounded-xl border-0 px-3 py-2.5 shadow-lg transition-shadow',
        selected && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
      )}
    >
      <Users className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <p className="line-clamp-2 text-sm font-medium text-foreground">{data.entry.name}</p>
    </div>
  )
}

const nodeTypes: NodeTypes = { character: CharacterNode }

/** Deterministic circular layout (task brief: a real force-directed graph is overkill for a
 * per-Book character count this small — React Flow's own pan/zoom/drag does the rest once
 * nodes have initial positions). A single node sits at the center rather than dividing by
 * zero. */
function layoutCircular(count: number, index: number): { x: number; y: number } {
  if (count <= 1) return { x: 0, y: 0 }
  const radius = 120 + count * 24
  const angle = (2 * Math.PI * index) / count - Math.PI / 2
  return { x: radius * Math.cos(angle), y: radius * Math.sin(angle) }
}

/**
 * The Characters tab's "map" view (PHASE-UI-EFFECTS.md §3): a book-wide relationship
 * overview distinct from the Canvas tab's scene/plot graph — nodes here are Codex
 * `entries`, not Scenes, and there is no `canvas_service`/scene-position state involved.
 * One node per character, one edge per `relationships` row (labeled with its
 * `relationship_type`), circularly arranged by array index. Clicking a node reuses the same
 * `onSelectEntry` callback the list view's cards call, so both views open the identical
 * `CodexEntryDialog` instance owned by `CharactersPanel`.
 */
export function CharacterRelationshipGraph({
  entries,
  relationships,
  onSelectEntry,
}: {
  entries: CodexEntry[]
  relationships: CodexRelationship[]
  onSelectEntry: (entry: CodexEntry) => void
}) {
  const nodes: CharacterFlowNode[] = useMemo(
    () =>
      entries.map((entry, index) => ({
        id: entry.id,
        type: 'character',
        position: layoutCircular(entries.length, index),
        data: { entry },
      })),
    [entries],
  )

  // Relationships pointing at a character not in this Book's `entries` (shouldn't happen —
  // `useBookCharacters` returns both from the same aggregation query — but guarded rather
  // than letting React Flow warn/crash on a dangling source/target id).
  const entryIds = useMemo(() => new Set(entries.map((entry) => entry.id)), [entries])
  const edges: Edge[] = useMemo(
    () =>
      relationships
        .filter((rel) => entryIds.has(rel.from_entry_id) && entryIds.has(rel.to_entry_id))
        .map((rel) => ({
          id: rel.id,
          source: rel.from_entry_id,
          target: rel.to_entry_id,
          label: rel.relationship_type,
          type: 'ink',
        })),
    [relationships, entryIds],
  )

  const handleNodeClick: NodeMouseHandler<CharacterFlowNode> = (_event, node) => {
    onSelectEntry(node.data.entry)
  }

  return (
    <div className="relative mt-0 h-[60vh] min-h-[420px] overflow-hidden rounded-2xl border border-border">
      <ReactFlowProvider>
        <ReactFlow<CharacterFlowNode, Edge>
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={{ type: 'ink' }}
          onNodeClick={handleNodeClick}
          fitView
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <Background className="!bg-background" gap={24} size={1} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  )
}

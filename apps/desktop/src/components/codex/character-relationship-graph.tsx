import { useMemo, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { Users } from 'lucide-react'
import { imageThumbUrl } from '@/queries/images'
import { RELATIONSHIP_TYPES, labelFor } from '@/lib/vocab'
import { useDelight } from '@/lib/delight'
import { cn } from '@/lib/utils'
import type { CodexEntry, CodexRelationship } from '@/lib/api'

/**
 * The Characters tab's "Map" view (PHASE-UI-EFFECTS.md §3; reworked in Phase 13 follow-up).
 *
 * A **read-only** book-wide relationship overview: one circular node per Codex character
 * (`entries`), one curved edge per `codex_relationships` row (`relationships`), rendered as a
 * hand-drawn SVG node-link graph rather than React Flow. Reengineered from a d3 rankings
 * bump-chart the user supplied — its *visual language* (circular nodes on a ring, thick
 * curved "swoosh" edges, a controls row, hover-to-highlight that dims everything else, and a
 * pointer-following tooltip) is reused, but the data it represents is who-relates-to-whom, not
 * ranks-over-years. Colors are the reference's colourful hsl-per-series idea applied per
 * relationship *type*, chosen at mid lightness so they read on both the Day and Night themes
 * (the reference's hardcoded dark palette is deliberately NOT used).
 *
 * Editing lives elsewhere by design: relationships are created/deleted in each character's
 * Relationships tab (`codex-entry-dialog.tsx`), and clicking a node here opens that same
 * `CodexEntryDialog` (via `onSelectEntry`). This surface never mutates data.
 *
 * NOTE (Phase 13 follow-up, `PHASE13.md`): this replaces the earlier drag-to-connect map.
 * `docs/16-PROTECTED-FEATURES.md` P9 still describes that older editable map and is
 * intentionally left unreconciled until the user unlocks it with the `spiderman` keyword — a
 * future session must not "restore" drag-to-connect here on the strength of P9's stale wording.
 */

interface NodePos {
  entry: CodexEntry
  x: number
  y: number
  angle: number
}

const NODE_R = 26
/** Curve control-point pull toward the ring centre — gives edges the reference's inward "swoosh". */
const BOW = 0.32

/** A stable, theme-legible colour per relationship type (mid lightness reads on Day + Night). */
function typeColor(typeIndex: number): string {
  return `hsl(${(typeIndex * 57 + 12) % 360} 70% 55%)`
}

/** First (up to) three characters of a name, uppercased — the fallback when a character has no
 * `primary_image_id`, matching the circular-chip convention used in the Canvas Codex drawer. */
function initials(name: string): string {
  return name.trim().slice(0, 3).toUpperCase() || '?'
}

export function CharacterRelationshipGraph({
  entries,
  relationships,
  onSelectEntry,
}: {
  entries: CodexEntry[]
  relationships: CodexRelationship[]
  onSelectEntry: (entry: CodexEntry) => void
}) {
  const { motionOk } = useDelight()
  const [activeType, setActiveType] = useState<string>('all')
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; entry: CodexEntry } | null>(null)

  // Node ring layout — deterministic, index-ordered; a single character sits at the centre
  // rather than dividing by zero (same posture as the old `layoutCircular`).
  const { nodes, posById, viewBox } = useMemo(() => {
    const count = entries.length
    const ringRadius = count <= 1 ? 0 : Math.max(150, 96 + count * 26)
    const nodes: NodePos[] = entries.map((entry, index) => {
      if (count <= 1) return { entry, x: 0, y: 0, angle: -Math.PI / 2 }
      const angle = (2 * Math.PI * index) / count - Math.PI / 2
      return { entry, x: ringRadius * Math.cos(angle), y: ringRadius * Math.sin(angle), angle }
    })
    const posById = new Map(nodes.map((node) => [node.entry.id, node]))
    // Pad the viewBox for the node radius + the label that hangs below each node.
    const pad = NODE_R + 46
    const half = ringRadius + pad
    const size = half * 2
    const viewBox = `${-half} ${-half} ${size} ${size}`
    return { nodes, posById, viewBox }
  }, [entries])

  const entryIds = useMemo(() => new Set(entries.map((entry) => entry.id)), [entries])

  // Only relationships whose BOTH ends are on this Book's roster (guards a dangling id from
  // crashing the render).
  const validRels = useMemo(
    () => relationships.filter((rel) => entryIds.has(rel.from_entry_id) && entryIds.has(rel.to_entry_id)),
    [relationships, entryIds],
  )

  const distinctTypes = useMemo(
    () => Array.from(new Set(validRels.map((rel) => rel.relationship_type))),
    [validRels],
  )

  // One stable colour per relationship type, shared by the edges AND the legend/controls
  // swatches so the map and its legend never disagree.
  const colorByType = useMemo(
    () => new Map(distinctTypes.map((type, index) => [type, typeColor(index)])),
    [distinctTypes],
  )

  const visibleRels = useMemo(
    () => (activeType === 'all' ? validRels : validRels.filter((rel) => rel.relationship_type === activeType)),
    [validRels, activeType],
  )

  // Neighbours of the hovered node, over the currently-visible edges only — drives the
  // dim-everything-else highlight.
  const neighborIds = useMemo(() => {
    if (!hoveredId) return null
    const set = new Set<string>([hoveredId])
    for (const rel of visibleRels) {
      if (rel.from_entry_id === hoveredId) set.add(rel.to_entry_id)
      else if (rel.to_entry_id === hoveredId) set.add(rel.from_entry_id)
    }
    return set
  }, [hoveredId, visibleRels])

  // Per-character relationship summary for the tooltip ("Ally → Bob").
  const relationsByEntry = useMemo(() => {
    const map = new Map<string, string[]>()
    const nameFor = (id: string) => posById.get(id)?.entry.name ?? id
    for (const rel of visibleRels) {
      const label = labelFor(RELATIONSHIP_TYPES, rel.relationship_type)
      const push = (id: string, text: string) => map.set(id, [...(map.get(id) ?? []), text])
      push(rel.from_entry_id, `${label} → ${nameFor(rel.to_entry_id)}`)
      push(rel.to_entry_id, `${label} ← ${nameFor(rel.from_entry_id)}`)
    }
    return map
  }, [visibleRels, posById])

  function handleContainerPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!hoveredId) return
    const rect = event.currentTarget.getBoundingClientRect()
    const entry = posById.get(hoveredId)?.entry
    if (entry) setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top, entry })
  }

  function enterNode(entry: CodexEntry) {
    setHoveredId(entry.id)
  }
  function leaveNode() {
    setHoveredId(null)
    setTooltip(null)
  }
  function handleNodeKeyDown(event: KeyboardEvent<SVGGElement>, entry: CodexEntry) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelectEntry(entry)
    }
  }

  if (entries.length === 0) {
    return (
      <div className="glass glass-edge flex h-[60vh] min-h-[420px] flex-col items-center justify-center gap-3 rounded-2xl p-6 text-center">
        <Users className="size-8 text-muted-foreground" aria-hidden="true" />
        <p className="max-w-xs text-sm text-muted-foreground">No characters to map yet.</p>
      </div>
    )
  }

  const transition = motionOk ? 'opacity 200ms ease, stroke-width 200ms ease' : undefined

  return (
    <div
      className="relative h-[60vh] min-h-[420px] overflow-hidden rounded-2xl border border-border bg-background"
      onPointerMove={handleContainerPointerMove}
    >
      {/* Controls row doubles as the LEGEND — one chip per relationship type, each showing its
          edge colour, and clicking it filters the map to that type (dashed → solid on active,
          the reference chart's control styling adapted to the app's tokens). Real buttons,
          keyboard-operable, in a tablist. */}
      {distinctTypes.length > 0 && (
        <div
          className="glass glass-edge absolute top-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-1 rounded-2xl p-1"
          role="tablist"
          aria-label="Filter relationships by type"
        >
          {['all', ...distinctTypes].map((type) => {
            const isActive = activeType === type
            const swatch = type === 'all' ? null : colorByType.get(type)
            return (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setActiveType(type)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium capitalize',
                  'focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                  motionOk && 'transition-colors',
                  isActive
                    ? 'border-solid border-primary bg-primary/15 text-primary'
                    : 'border-dashed border-border text-muted-foreground hover:bg-accent',
                )}
              >
                {swatch && (
                  <span
                    aria-hidden="true"
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: swatch }}
                  />
                )}
                {type === 'all' ? 'All' : labelFor(RELATIONSHIP_TYPES, type)}
              </button>
            )
          })}
        </div>
      )}

      {validRels.length === 0 && (
        <p className="absolute inset-x-0 bottom-4 z-10 px-6 text-center text-xs text-muted-foreground">
          Add relationships in a character&rsquo;s Relationships tab to see connections here.
        </p>
      )}

      <svg
        viewBox={viewBox}
        className="h-full w-full"
        style={{ fontFamily: 'inherit' }}
        role="group"
        aria-label="Character relationship map"
      >
        {/* Edges (behind nodes). Quadratic Bézier bowed toward the ring centre for the swoosh. */}
        <g fill="none" strokeLinecap="round">
          {visibleRels.map((rel) => {
            const a = posById.get(rel.from_entry_id)
            const b = posById.get(rel.to_entry_id)
            if (!a || !b) return null
            const color = colorByType.get(rel.relationship_type) ?? 'currentColor'
            const cx = ((a.x + b.x) / 2) * (1 - BOW)
            const cy = ((a.y + b.y) / 2) * (1 - BOW)
            const active = !neighborIds || neighborIds.has(rel.from_entry_id) || neighborIds.has(rel.to_entry_id)
            return (
              <path
                key={rel.id}
                d={`M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`}
                stroke={color}
                strokeWidth={active ? 4 : 3}
                opacity={active ? 0.9 : 0.12}
                style={{ transition }}
              >
                <title>{`${labelFor(RELATIONSHIP_TYPES, rel.relationship_type)}: ${a.entry.name} → ${b.entry.name}`}</title>
              </path>
            )
          })}
        </g>

        {/* Nodes (front). Focusable + clickable → open the character's editor. */}
        {nodes.map(({ entry, x, y }) => {
          const active = !neighborIds || neighborIds.has(entry.id)
          const clipId = `crg-clip-${entry.id}`
          return (
            <g
              key={entry.id}
              role="button"
              tabIndex={0}
              aria-label={`${entry.name} — open character`}
              transform={`translate(${x} ${y})`}
              className="cursor-pointer outline-none"
              opacity={active ? 1 : 0.25}
              style={{ transition }}
              onClick={() => onSelectEntry(entry)}
              onKeyDown={(event) => handleNodeKeyDown(event, entry)}
              onPointerEnter={() => enterNode(entry)}
              onPointerLeave={leaveNode}
              onFocus={() => enterNode(entry)}
              onBlur={leaveNode}
            >
              {entry.primary_image_id && (
                <clipPath id={clipId}>
                  <circle r={NODE_R} />
                </clipPath>
              )}
              <circle
                r={NODE_R}
                fill="var(--card)"
                stroke={hoveredId === entry.id ? 'var(--primary)' : 'var(--border)'}
                strokeWidth={hoveredId === entry.id ? 3.5 : 2}
              />
              {entry.primary_image_id ? (
                <image
                  href={imageThumbUrl(entry.primary_image_id)}
                  x={-NODE_R}
                  y={-NODE_R}
                  width={NODE_R * 2}
                  height={NODE_R * 2}
                  clipPath={`url(#${clipId})`}
                  preserveAspectRatio="xMidYMid slice"
                />
              ) : (
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="var(--foreground)"
                  fontSize={13}
                  fontWeight={700}
                >
                  {initials(entry.name)}
                </text>
              )}
              <text
                textAnchor="middle"
                y={NODE_R + 16}
                fill="var(--foreground)"
                fontSize={11}
                fontWeight={600}
              >
                {entry.name.length > 16 ? `${entry.name.slice(0, 15)}…` : entry.name}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Pointer-following tooltip — the character's name + its (type-filtered) relationships. */}
      {tooltip && (
        <div
          className="glass glass-edge pointer-events-none absolute z-20 max-w-56 -translate-x-1/2 -translate-y-full rounded-lg px-3 py-2 text-xs shadow-lg"
          style={{ left: tooltip.x, top: tooltip.y - 10 }}
        >
          <p className="text-sm font-semibold text-foreground">{tooltip.entry.name}</p>
          {(() => {
            const rels = relationsByEntry.get(tooltip.entry.id)
            return rels && rels.length > 0 ? (
              <ul className="mt-1 space-y-0.5 text-muted-foreground">
                {rels.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-muted-foreground">No relationships yet.</p>
            )
          })()}
        </div>
      )}
    </div>
  )
}

import { useMemo } from 'react'
import { scaleBand } from 'd3-scale'
import { CalendarClock } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useDelight } from '@/lib/delight'
import { cn } from '@/lib/utils'
import type { CodexEntry } from '@/lib/api'
import type { TimelineRow } from '@/components/outline/timeline-view'

const CELL_WIDTH = 36
const ROW_HEIGHT = 40
const MARKER_SIZE = 16
const LABEL_WIDTH = 168

/**
 * The Characters tab's "Timeline" view (PHASE-UI-EFFECTS-2.md §3/§5 task 8): a Gantt-style
 * presence chart, one row per character, x-axis = the Book's scenes in chronological
 * (`timeline_order_index`) order — the same order the Outline tab's Timeline view already
 * renders (`scenes` here is built by `timeline-view.tsx`'s own `buildRows`, passed down from
 * `CharactersPanel` rather than re-derived here).
 *
 * `d3-scale`'s `scaleBand` computes each scene's x-position/bandwidth only — every mark is a
 * plain React-rendered `<button>` (no `<svg>`/`foreignObject`), matching the rest of this
 * codebase's DOM-based row/grid components (`beat-board.tsx`, `timeline-view.tsx`) rather
 * than introducing a canvas/SVG rendering surface with no other precedent in this app.
 *
 * A character's row shows a mark only at scenes present in `sceneLinks[entry.id]` — gaps are
 * scenes the character doesn't appear in, exactly the "appears/disappears/overlaps" Gantt
 * reading the design doc calls for.
 */
export function CharacterSceneTimeline({
  entries,
  sceneLinks,
  scenes,
}: {
  entries: CodexEntry[]
  /** `CharacterMapResponse.scene_links` — keyed by `codex_entry_id`, values are `scene_id`s. */
  sceneLinks: Record<string, string[]>
  /** The Outline tab's chronological scene order (`timeline-view.tsx`'s `buildRows` output) — this view's x-axis. */
  scenes: TimelineRow[]
}) {
  const { motionOk } = useDelight()

  const xScale = useMemo(
    () =>
      scaleBand<string>()
        .domain(scenes.map((scene) => scene.sceneId))
        .range([0, Math.max(scenes.length, 1) * CELL_WIDTH])
        .paddingInner(0.35)
        .paddingOuter(0.5),
    [scenes],
  )

  const trackWidth = xScale.range()[1]

  if (scenes.length === 0 || entries.length === 0) {
    return (
      <div className="glass glass-edge flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-2xl p-6 text-center">
        <CalendarClock className="size-8 text-muted-foreground" aria-hidden="true" />
        <p className="max-w-xs text-sm text-muted-foreground">
          {entries.length === 0
            ? 'No characters match this view yet.'
            : 'Add scenes on the Canvas and place them on the Outline’s Timeline view to see character presence here.'}
        </p>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'glass glass-edge overflow-x-auto rounded-2xl p-3',
        motionOk && 'animate-in fade-in-0 duration-300',
      )}
    >
      <div className="flex" style={{ width: LABEL_WIDTH + trackWidth }}>
        <div className="sticky left-0 z-10 flex shrink-0 flex-col" style={{ width: LABEL_WIDTH }}>
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="flex items-center truncate border-r border-border/60 bg-card/60 pr-3 pl-1 text-sm font-medium backdrop-blur-sm"
              style={{ height: ROW_HEIGHT }}
            >
              <span className="truncate">{entry.name}</span>
            </div>
          ))}
        </div>

        <div className="relative shrink-0" style={{ width: trackWidth, height: entries.length * ROW_HEIGHT }}>
          {/* Row baselines, purely decorative. */}
          {entries.map((_, rowIndex) => (
            <div
              key={rowIndex}
              aria-hidden="true"
              className="absolute right-0 left-0 border-b border-border/40"
              style={{ top: rowIndex * ROW_HEIGHT + ROW_HEIGHT / 2, height: 1 }}
            />
          ))}

          {entries.map((entry, rowIndex) => {
            const linkedSceneIds = new Set(sceneLinks[entry.id] ?? [])
            return scenes.map((scene, sceneIndex) => {
              if (!linkedSceneIds.has(scene.sceneId)) return null
              const bandStart = xScale(scene.sceneId) ?? 0
              const x = bandStart + xScale.bandwidth() / 2 - MARKER_SIZE / 2
              const y = rowIndex * ROW_HEIGHT + ROW_HEIGHT / 2 - MARKER_SIZE / 2
              const label = `${entry.name} appears in Scene ${sceneIndex + 1}: ${scene.title}`

              return (
                <Popover key={`${entry.id}-${scene.sceneId}`}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <PopoverTrigger asChild>
                        <button
                          type="button"
                          aria-label={label}
                          className={cn(
                            'absolute rounded-full bg-primary transition-colors hover:bg-primary/80',
                            'focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                          )}
                          style={{ left: x, top: y, width: MARKER_SIZE, height: MARKER_SIZE }}
                        />
                      </PopoverTrigger>
                    </TooltipTrigger>
                    <TooltipContent>{scene.title}</TooltipContent>
                  </Tooltip>
                  <PopoverContent className="w-64 text-sm">
                    <p className="font-medium">{scene.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Scene {sceneIndex + 1} of {scenes.length} · {entry.name}
                      {scene.label ? ` · ${scene.label}` : ''}
                    </p>
                  </PopoverContent>
                </Popover>
              )
            })
          })}
        </div>
      </div>
    </div>
  )
}

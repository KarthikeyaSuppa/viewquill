import { useMemo, useState } from 'react'
import {
  BookOpen,
  Check,
  ChevronLeft,
  Flag,
  MapPin,
  Pencil,
  Plus,
  Search,
  Trash2,
  Users,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  useCodexEntries,
  useCreateCodex,
  useDeleteCodex,
  useLinkCodexToScene,
  useSceneCodex,
  useUnlinkCodexFromScene,
} from '@/queries/codex'
import { CodexEntryDialog } from '@/components/codex/codex-entry-dialog'
import { useBooks } from '@/queries/books'
import { imageThumbUrl } from '@/queries/images'
import type { CodexEntry, CodexEntryType } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useSliceDelete } from '@/components/ui/slice-delete'

const TYPE_OPTIONS: { value: CodexEntryType; label: string; icon: typeof Users }[] = [
  { value: 'character', label: 'Characters', icon: Users },
  { value: 'location', label: 'Locations', icon: MapPin },
  { value: 'faction', label: 'Factions', icon: Flag },
  { value: 'object_lore', label: 'Object / Lore', icon: BookOpen },
]

/** Case-insensitive substring match against name or summary — same lightweight
 * filter pattern as `characters-panel.tsx`'s `matchesQuery` (the type filter above
 * already narrows to one of the four types, so this list is always small). */
function matchesQuery(entry: CodexEntry, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return entry.name.toLowerCase().includes(q) || (entry.summary?.toLowerCase().includes(q) ?? false)
}

/**
 * The Codex side panel (docs/01-PRODUCT-VISION.md §Codex, docs/03-DATA-MODEL.md
 * `codex_entries`/`codex_scene_links`, docs/06 Phase 2 task H3).
 *
 * A full-height left sidebar drawer (Phase 13 Workstream B) docked to the canvas area's
 * left edge — entries render as circular chips in a wrapping grid rather than pill rows,
 * so the drawer reads more like a character/asset rail than a list. Logic is unchanged
 * from the earlier bottom-left floating card: type filter + search + per-Scene
 * link/unlink toggle. Creating and editing entries both defer to the full
 * `CodexEntryDialog` (custom fields, relationships, image, arc states) rather than
 * duplicating any of that here — this panel only owns the grid, the type filter, and the
 * link-to-selected-node toggle. Defaults to Characters with a small filter for the other
 * three entry types.
 */
export function CodexPanel({ sceneId }: { sceneId: string | undefined }) {
  const [open, setOpen] = useState(false)
  const [entryType, setEntryType] = useState<CodexEntryType>('character')
  const [query, setQuery] = useState('')
  const [editingEntry, setEditingEntry] = useState<CodexEntry | null>(null)

  const { data: books } = useBooks()
  const { data: entries, isLoading } = useCodexEntries(entryType)
  const { data: sceneEntries } = useSceneCodex(sceneId)
  const linkedIds = useMemo(
    () => new Set((sceneEntries ?? []).map((entry) => entry.id)),
    [sceneEntries],
  )

  const createCodex = useCreateCodex()
  const linkToScene = useLinkCodexToScene(sceneId)
  const unlinkFromScene = useUnlinkCodexFromScene(sceneId)

  /** Creates a bare entry of the current filter type, then opens it in the full
   * `CodexEntryDialog` for naming/details — mirrors the dialog-driven create pattern
   * used elsewhere in the app rather than duplicating name/summary fields here. */
  function handleCreate() {
    const typeLabel = TYPE_OPTIONS.find((t) => t.value === entryType)?.label.replace(/s$/, '') ?? 'Entry'
    createCodex.mutate(
      { entry_type: entryType, name: `New ${typeLabel}` },
      { onSuccess: (created) => setEditingEntry(created) },
    )
  }

  function handleToggleLink(entry: CodexEntry) {
    if (!sceneId) return
    if (linkedIds.has(entry.id)) {
      unlinkFromScene.mutate(entry.id)
    } else {
      linkToScene.mutate(entry.id)
    }
  }

  if (!open) {
    return (
      <div className="pointer-events-auto absolute left-4 top-4 z-10">
        <Button size="sm" variant="secondary" className="glass glass-edge" onClick={() => setOpen(true)}>
          <Users className="size-4" />
          Codex
        </Button>
      </div>
    )
  }

  const allRows = entries ?? []
  const rows = allRows.filter((entry) => matchesQuery(entry, query))
  const activeTypeOption = TYPE_OPTIONS.find((t) => t.value === entryType)

  return (
    <div className="glass glass-edge pointer-events-auto absolute inset-y-0 left-0 z-10 flex w-80 flex-col overflow-hidden rounded-r-2xl">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2.5">
        <span className="text-sm font-semibold">Codex</span>
        <Button variant="ghost" size="icon-sm" aria-label="Collapse Codex panel" onClick={() => setOpen(false)}>
          <ChevronLeft className="size-4" />
        </Button>
      </div>

      <div className="flex flex-col gap-2 border-b border-border px-3 py-2.5">
        <Select value={entryType} onValueChange={(value) => setEntryType(value as CodexEntryType)}>
          <SelectTrigger size="sm" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TYPE_OPTIONS.map(({ value, label, icon: Icon }) => (
              <SelectItem key={value} value={value}>
                <Icon className="size-3.5" />
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="relative">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Filter ${activeTypeOption?.label.toLowerCase() ?? 'entries'}…`}
            aria-label={`Filter ${activeTypeOption?.label.toLowerCase() ?? 'entries'} by name or summary`}
            autoComplete="off"
            className="h-8 pl-8 text-sm"
          />
        </div>

        {sceneId && (
          <p className="text-xs text-muted-foreground">
            Click a circle to attach/detach it from the selected node.
          </p>
        )}
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-wrap gap-3 p-3">
          {isLoading ? (
            <p className="w-full text-xs text-muted-foreground">Loading…</p>
          ) : allRows.length === 0 ? (
            <p className="w-full text-xs text-muted-foreground">
              No {activeTypeOption?.label.toLowerCase()} yet.
            </p>
          ) : rows.length === 0 ? (
            <p className="w-full text-xs text-muted-foreground">
              No {activeTypeOption?.label.toLowerCase()} match “{query.trim()}”.
            </p>
          ) : (
            rows.map((entry) => (
              <CodexEntryChip
                key={entry.id}
                entry={entry}
                linked={sceneId ? linkedIds.has(entry.id) : undefined}
                linkPending={linkToScene.isPending || unlinkFromScene.isPending}
                onToggleLink={sceneId ? () => handleToggleLink(entry) : undefined}
                onOpenEditor={() => setEditingEntry(entry)}
              />
            ))
          )}
        </div>
      </ScrollArea>

      <div className="border-t border-border px-3 py-2.5">
        <Button
          variant="secondary"
          size="sm"
          onClick={handleCreate}
          disabled={createCodex.isPending}
          className="w-full"
        >
          <Plus className="size-3.5" />
          New {activeTypeOption?.label.replace(/s$/, '')}
        </Button>
      </div>

      {editingEntry && (
        <CodexEntryDialog
          entry={editingEntry}
          open={!!editingEntry}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) setEditingEntry(null)
          }}
          books={books}
        />
      )}
    </div>
  )
}

/** One Codex entry as a circular chip — image thumbnail (or initials) in a circle, name
 * underneath, link state as a ring/checkmark badge on the circle itself, and edit/delete
 * surfaced via a small hover/focus overlay so the circle stays the primary, uncluttered
 * link/unlink target. */
function CodexEntryChip({
  entry,
  linked,
  linkPending,
  onToggleLink,
  onOpenEditor,
}: {
  entry: CodexEntry
  /** undefined when no canvas node is selected — the circle then falls back to opening the
   * editor on click, with a tooltip explaining why linking isn't available (discoverability
   * preserved even without a rectangular disabled-button affordance). */
  linked: boolean | undefined
  linkPending: boolean
  onToggleLink: (() => void) | undefined
  /** Opens the full CodexEntryDialog (custom fields, relationships, image, arc states). */
  onOpenEditor: () => void
}) {
  const deleteCodex = useDeleteCodex()
  const linkAvailable = onToggleLink !== undefined
  const initials = entry.name.trim().slice(0, 3).toUpperCase() || '?'

  // Slice-to-delete removal (Playful + motion only, instant everywhere else — see
  // `components/ui/slice-delete.tsx`). The confirm dialog and the delete mutation itself
  // are unchanged; this only delays the chip's visual unmount by the animation, and
  // `onCommit` is guaranteed to still fire even if it's interrupted (see that file).
  const sliceDelete = useSliceDelete(() => deleteCodex.mutate(entry.id), 'chip')

  return (
    <div
      className={cn('group relative flex w-20 flex-col items-center gap-1', sliceDelete.className)}
      onAnimationEnd={sliceDelete.onAnimationEnd}
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onToggleLink ?? onOpenEditor}
            disabled={linkAvailable && linkPending}
            aria-pressed={linkAvailable ? linked : undefined}
            aria-label={
              !linkAvailable
                ? `Select a node on canvas to link “${entry.name}” — opens editor instead`
                : linked
                  ? `Unlink “${entry.name}” from selected node`
                  : `Link “${entry.name}” to selected node`
            }
            className={cn(
              'relative flex size-16 items-center justify-center overflow-hidden rounded-full border-2 bg-muted text-sm font-semibold text-muted-foreground transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none',
              linked ? 'border-primary text-primary' : 'border-border hover:border-primary/50',
            )}
          >
            {entry.primary_image_id ? (
              <img
                src={imageThumbUrl(entry.primary_image_id)}
                alt=""
                className="size-full object-cover"
              />
            ) : (
              initials
            )}

            {linked && (
              <span className="absolute right-0 bottom-0 flex size-5 items-center justify-center rounded-full border-2 border-background bg-primary text-primary-foreground">
                <Check className="size-3" />
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent>
          {entry.name}
          {' — '}
          {!linkAvailable
            ? 'select a node on canvas to link (click opens editor)'
            : linked
              ? 'linked to selected node — click to unlink'
              : 'click to link to selected node'}
        </TooltipContent>
      </Tooltip>

      {/* Edit/delete overlay — hidden until the chip is hovered or focused so the circle
          itself stays the clean, primary link/unlink target. */}
      <div className="absolute -top-1 -right-1 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="secondary"
              size="icon-sm"
              className="size-6 rounded-full shadow-sm"
              aria-label={`Edit “${entry.name}”`}
              onClick={onOpenEditor}
            >
              <Pencil className="size-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Edit — name, custom fields, relationships, image, arc states</TooltipContent>
        </Tooltip>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              variant="secondary"
              size="icon-sm"
              className="size-6 rounded-full shadow-sm"
              aria-label={`Delete “${entry.name}”`}
              disabled={deleteCodex.isPending}
            >
              <Trash2 className="size-3" />
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete “{entry.name}” forever?</AlertDialogTitle>
              <AlertDialogDescription>
                This permanently deletes this Codex entry, including its links to every
                Scene and Book. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction variant="destructive" onClick={sliceDelete.startRemove}>
                Delete permanently
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <p className="line-clamp-2 w-full text-center text-xs text-muted-foreground">{entry.name}</p>
    </div>
  )
}

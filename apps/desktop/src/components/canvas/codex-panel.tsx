import { useMemo, useState } from 'react'
import {
  BookOpen,
  ChevronDown,
  Flag,
  Link2,
  MapPin,
  Pencil,
  Plus,
  Search,
  Trash2,
  Unlink2,
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
import type { CodexEntry, CodexEntryType } from '@/lib/api'
import { cn } from '@/lib/utils'

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
 * Canvas-scoped quick view over the Codex: list + filter + per-Scene link/unlink toggle.
 * Creating and editing entries both defer to the full `CodexEntryDialog` (custom fields,
 * relationships, image, arc states) rather than duplicating any of that here — this panel
 * only owns the list, the type filter, and the link-to-selected-node toggle. Defaults to
 * Characters with a small filter for the other three entry types.
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
      <div className="pointer-events-auto absolute bottom-4 left-4 z-10">
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
    <div className="glass glass-edge pointer-events-auto absolute bottom-4 left-4 z-10 flex max-h-[65%] w-80 flex-col overflow-hidden rounded-2xl">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2.5">
        <span className="text-sm font-semibold">Codex</span>
        <Button variant="ghost" size="icon-sm" aria-label="Collapse Codex panel" onClick={() => setOpen(false)}>
          <ChevronDown className="size-4" />
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
            <Link2 className="mr-1 inline size-3" />
            Toggle the link icon to attach/detach an entry from the selected node.
          </p>
        )}
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col gap-2 px-3 py-2.5">
          {isLoading ? (
            <p className="text-xs text-muted-foreground">Loading…</p>
          ) : allRows.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No {activeTypeOption?.label.toLowerCase()} yet.
            </p>
          ) : rows.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No {activeTypeOption?.label.toLowerCase()} match “{query.trim()}”.
            </p>
          ) : (
            rows.map((entry) => (
              <CodexEntryRow
                key={entry.id}
                entry={entry}
                icon={activeTypeOption?.icon}
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

/** One Codex entry row — type icon + name/summary, a link toggle, an edit button that opens
 * the full `CodexEntryDialog`, and delete. */
function CodexEntryRow({
  entry,
  icon: TypeIcon,
  linked,
  linkPending,
  onToggleLink,
  onOpenEditor,
}: {
  entry: CodexEntry
  /** The active type filter's icon (from `TYPE_OPTIONS`) — shown small next to the name so a
   * row's type reads at a glance even though the list is always pre-filtered to one type. */
  icon: typeof Users | undefined
  /** undefined when no canvas node is selected — the link toggle then renders disabled with a
   * tooltip explaining why, rather than disappearing outright (discoverability). */
  linked: boolean | undefined
  linkPending: boolean
  onToggleLink: (() => void) | undefined
  /** Opens the full CodexEntryDialog (custom fields, relationships, image, arc states). */
  onOpenEditor: () => void
}) {
  const deleteCodex = useDeleteCodex()
  const linkAvailable = onToggleLink !== undefined

  return (
    <div className="flex items-start gap-1.5 rounded-lg border border-border p-2 transition-colors hover:bg-accent/40">
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 truncate text-sm font-medium">
          {TypeIcon && <TypeIcon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />}
          <span className="truncate">{entry.name}</span>
        </p>
        {entry.summary && <p className="line-clamp-2 text-xs text-muted-foreground">{entry.summary}</p>}
      </div>

      <div className="flex shrink-0 items-center gap-0.5">
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button
                variant={linked ? 'secondary' : 'ghost'}
                size="icon-sm"
                onClick={onToggleLink}
                disabled={!linkAvailable || linkPending}
                aria-pressed={linkAvailable ? linked : undefined}
                aria-label={
                  !linkAvailable
                    ? 'Select a node on canvas to link'
                    : linked
                      ? 'Unlink from selected node'
                      : 'Link to selected node'
                }
                className={cn(linked && 'text-primary')}
              >
                {linked ? <Unlink2 className="size-3.5" /> : <Link2 className="size-3.5" />}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {!linkAvailable
              ? 'Select a node on canvas to link'
              : linked
                ? 'Linked to selected node — click to unlink'
                : 'Link to selected node'}
          </TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Edit entry" onClick={onOpenEditor}>
              <Pencil className="size-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Edit — name, custom fields, relationships, image, arc states</TooltipContent>
        </Tooltip>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label="Delete entry" disabled={deleteCodex.isPending}>
              <Trash2 className="size-3.5" />
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
              <AlertDialogAction variant="destructive" onClick={() => deleteCodex.mutate(entry.id)}>
                Delete permanently
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  )
}

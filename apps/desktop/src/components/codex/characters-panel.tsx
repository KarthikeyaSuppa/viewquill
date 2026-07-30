import { useMemo, useState } from 'react'
import { List, Network, Plus, Search, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import { useBookCharacters, useCreateCodex, useLinkCodexToBook } from '@/queries/codex'
import { useBooks } from '@/queries/books'
import { CodexEntryDialog } from '@/components/codex/codex-entry-dialog'
import { CharacterRelationshipGraph } from '@/components/codex/character-relationship-graph'
import type { CodexEntry } from '@/lib/api'
import { cn } from '@/lib/utils'

/** View-mode seam for the relationship-graph "map" view (PHASE-UI-EFFECTS.md §3 task 4,
 * React Flow over `codex_relationships`): `'list'` is the searchable card grid, `'map'`
 * renders `CharacterRelationshipGraph` below. Both branches share the same `filtered`
 * entries and the same `editingEntry`/`CodexEntryDialog` state. */
type CharactersViewMode = 'list' | 'map'

/** Case-insensitive substring match against name or summary — the whole small per-Book
 * character set is already in memory, so this runs on every keystroke with no debounce
 * (PHASE-UI-EFFECTS.md §3: "Phase 10's hybrid search is overkill at this scale"). */
function matchesQuery(entry: CodexEntry, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return entry.name.toLowerCase().includes(q) || (entry.summary?.toLowerCase().includes(q) ?? false)
}

/**
 * The Book screen's Characters tab (PHASE-UI-EFFECTS.md §3): a searchable list of the
 * Book's character-type Codex entries (`useBookCharacters`), each a real `<button>` card
 * that opens the existing `CodexEntryDialog` full editor — no second entry-editing UI.
 *
 * Empty state offers an inline "Add character" form that reuses `useCreateCodex` (the same
 * mutation `codex-panel.tsx` uses for creation) plus `useLinkCodexToBook` so the new entry
 * is immediately scoped to this Book and shows up in the list without a refetch race.
 *
 * Accessibility: labeled search input, cards are native buttons (keyboard-navigable via
 * Tab/Enter with no extra wiring), and loading/empty/filtered-count states are announced
 * via a visually-hidden `role="status"` region, mirroring `backup-nudge.tsx`/`search-dialog.tsx`.
 */
export function CharactersPanel({ bookId }: { bookId: string }) {
  const [viewMode, setViewMode] = useState<CharactersViewMode>('list')
  const [query, setQuery] = useState('')
  const [editingEntry, setEditingEntry] = useState<CodexEntry | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newSummary, setNewSummary] = useState('')

  const { data, isLoading } = useBookCharacters(bookId)
  const { data: books } = useBooks()
  const createCodex = useCreateCodex()
  const linkToBook = useLinkCodexToBook(bookId)

  const entries = useMemo(() => data?.entries ?? [], [data])
  const relationships = useMemo(() => data?.relationships ?? [], [data])
  const filtered = useMemo(() => entries.filter((entry) => matchesQuery(entry, query)), [entries, query])

  const nameInvalid = newName.trim().length === 0
  const addPending = createCodex.isPending || linkToBook.isPending

  function handleCreate() {
    if (nameInvalid) return
    createCodex.mutate(
      { entry_type: 'character', name: newName.trim(), summary: newSummary.trim() || null },
      {
        onSuccess: (entry) => {
          linkToBook.mutate(entry.id)
          setNewName('')
          setNewSummary('')
          setCreating(false)
        },
      },
    )
  }

  const trimmedQuery = query.trim()
  const statusText = isLoading
    ? 'Loading characters…'
    : entries.length === 0
      ? 'No characters yet.'
      : trimmedQuery
        ? `${filtered.length} of ${entries.length} character${entries.length === 1 ? '' : 's'} match “${trimmedQuery}”.`
        : `${entries.length} character${entries.length === 1 ? '' : 's'}.`

  return (
    <div className="mt-4 flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-[220px] max-w-sm flex-1 space-y-1.5">
          <Label htmlFor="characters-search">Search characters</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              id="characters-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by name or summary…"
              className="pl-8"
              autoComplete="off"
            />
          </div>
        </div>

        {/* List/Map view toggle (PHASE-UI-EFFECTS.md §3 task 4) — native `<button>`s in a
            `role="tablist"`, same pattern as `outline-panel.tsx`'s Outline/Timeline toggle,
            so it's keyboard-operable (Tab + Enter/Space) with no extra wiring. */}
        <div
          className="glass glass-edge flex items-center gap-1 rounded-full p-1"
          role="tablist"
          aria-label="List or Map view"
        >
          <Button
            type="button"
            size="sm"
            variant={viewMode === 'list' ? 'secondary' : 'ghost'}
            className="rounded-full"
            role="tab"
            aria-selected={viewMode === 'list'}
            onClick={() => setViewMode('list')}
          >
            <List className="size-4" />
            List
          </Button>
          <Button
            type="button"
            size="sm"
            variant={viewMode === 'map' ? 'secondary' : 'ghost'}
            className="rounded-full"
            role="tab"
            aria-selected={viewMode === 'map'}
            onClick={() => setViewMode('map')}
          >
            <Network className="size-4" />
            Map
          </Button>
        </div>

        <Button size="sm" onClick={() => setCreating((prev) => !prev)}>
          <Plus className="size-4" />
          Add character
        </Button>
      </div>

      {creating && (
        <div className="glass glass-edge flex flex-col gap-2 rounded-xl p-3">
          <Label htmlFor="new-character-name" className="text-xs">
            Name
          </Label>
          <Input
            id="new-character-name"
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            aria-invalid={nameInvalid}
            className="h-8 text-sm"
          />
          <Textarea
            value={newSummary}
            onChange={(event) => setNewSummary(event.target.value)}
            placeholder="Summary (optional)"
            className="min-h-14 text-xs"
          />
          <div className="flex items-center gap-1.5">
            <Button size="sm" onClick={handleCreate} disabled={nameInvalid || addPending}>
              <Plus className="size-3.5" />
              Add
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div role="status" aria-live="polite" className="sr-only">
        {statusText}
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading characters…</p>
      ) : entries.length === 0 ? (
        <div className="glass glass-edge flex min-h-[200px] flex-col items-center justify-center gap-3 rounded-2xl p-6 text-center">
          <Users className="size-8 text-muted-foreground" aria-hidden="true" />
          <p className="max-w-xs text-sm text-muted-foreground">
            No characters linked to this Book yet. Add one to start tracking them here.
          </p>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            Add character
          </Button>
        </div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">No characters match “{trimmedQuery}”.</p>
      ) : viewMode === 'list' ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => setEditingEntry(entry)}
              className={cn(
                'rounded-xl text-left transition-colors',
                'focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
              )}
            >
              <Card className="h-full gap-1.5 py-4 transition-colors hover:bg-accent/50">
                <CardContent className="px-4">
                  <p className="truncate text-sm font-medium">{entry.name}</p>
                  {entry.summary && (
                    <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">{entry.summary}</p>
                  )}
                </CardContent>
              </Card>
            </button>
          ))}
        </div>
      ) : (
        <CharacterRelationshipGraph
          entries={filtered}
          relationships={relationships}
          onSelectEntry={setEditingEntry}
        />
      )}

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

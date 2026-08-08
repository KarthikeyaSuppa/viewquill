import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { List, Loader2, Network, Plus, Search, UserPlus, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useBookCharacters, useCodexEntries, useCreateCodex, useLinkCodexToBook } from '@/queries/codex'
import { useBooks } from '@/queries/books'
import { CodexEntryDialog } from '@/components/codex/codex-entry-dialog'
import { CharacterRelationshipGraph } from '@/components/codex/character-relationship-graph'
import type { CodexEntry } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useDelight } from '@/lib/delight'

/** View-mode seam for the relationship-graph "map" view (PHASE-UI-EFFECTS.md §3 task 4,
 * React Flow over `codex_relationships`): `'list'` is the searchable card grid, `'map'`
 * renders `CharacterRelationshipGraph`. Both branches share the same `filtered` entries and
 * the same `editingEntry`/`CodexEntryDialog` state. (The Gantt-style "timeline" view from
 * PHASE-UI-EFFECTS-2.md §3/§5 task 8 was removed in PHASE13 Workstream A.) */
type CharactersViewMode = 'list' | 'map'

/** Case-insensitive substring match against name or summary — the whole small per-Book
 * character set is already in memory, so this runs on every keystroke with no debounce
 * (PHASE-UI-EFFECTS.md §3: "Phase 10's hybrid search is overkill at this scale"). */
function matchesQuery(entry: CodexEntry, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  return entry.name.toLowerCase().includes(q) || (entry.summary?.toLowerCase().includes(q) ?? false)
}

const ALPHABET = Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i))

/** First letter of a name, uppercased, bucketed to `'#'` for anything that doesn't start
 * with A-Z (numerals, punctuation) — those entries still render, just outside the rail. */
function letterBucket(name: string): string {
  const ch = name.trim().charAt(0).toUpperCase()
  return ch >= 'A' && ch <= 'Z' ? ch : '#'
}

/** Groups `entries` into contiguous per-first-letter sections, sorted case-insensitively by
 * name with the `'#'` bucket pinned last regardless of locale. The A-Z index rail (§2 task 9,
 * PHASE-UI-EFFECTS-2.md §2 item 1) only makes sense against an alphabetized list — "jump to
 * the first name starting with C" and "highlight the letter currently in view" both assume
 * same-letter entries are contiguous — so List view sorts here; Map keeps the original
 * (unsorted) `filtered` order since it has no comparable per-letter concept. */
function groupByLetter(entries: CodexEntry[]): [string, CodexEntry[]][] {
  const sorted = [...entries].sort((a, b) => {
    const bucketA = letterBucket(a.name)
    const bucketB = letterBucket(b.name)
    if (bucketA !== bucketB) {
      if (bucketA === '#') return 1
      if (bucketB === '#') return -1
      return bucketA < bucketB ? -1 : 1
    }
    return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  })
  const groups: [string, CodexEntry[]][] = []
  for (const entry of sorted) {
    const letter = letterBucket(entry.name)
    const last = groups[groups.length - 1]
    if (last && last[0] === letter) last[1].push(entry)
    else groups.push([letter, [entry]])
  }
  return groups
}

/**
 * Vertical A-Z jump rail for the Characters List view (PHASE-UI-EFFECTS-2.md §2 item 1, §5
 * task 9). Every letter renders as a real `<button>` (never hover-only) so it's reachable via
 * Tab/Enter; letters absent from the current (already search-filtered) results are `disabled`
 * and dimmed rather than removed, matching the common "grayed-out unavailable index letter"
 * pattern so the rail's shape doesn't jump around as the user types a filter.
 *
 * The highlight itself (`active === letter`) always applies instantly — only the CSS
 * `transition-colors` on top of it is gated by `motionOk`, per `wobbly-indicator.tsx`'s
 * convention: decoration is gated, the affordance (which letter is current) never is.
 */
function AlphabetIndexRail({
  available,
  active,
  motionOk,
  onJump,
}: {
  available: Set<string>
  active: string | null
  motionOk: boolean
  onJump: (letter: string) => void
}) {
  return (
    <div
      className="glass glass-edge sticky top-4 flex max-h-[70vh] flex-col items-center gap-0.5 self-start overflow-y-auto rounded-full px-1 py-2"
      role="navigation"
      aria-label="Jump to character name"
    >
      {ALPHABET.map((letter) => {
        const isAvailable = available.has(letter)
        const isActive = isAvailable && active === letter
        return (
          <button
            key={letter}
            type="button"
            disabled={!isAvailable}
            onClick={() => onJump(letter)}
            aria-label={`Jump to names starting with ${letter}`}
            aria-current={isActive ? 'true' : undefined}
            className={cn(
              'flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] leading-none font-medium',
              'focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
              isAvailable
                ? 'text-foreground/70 hover:bg-accent'
                : 'cursor-default text-muted-foreground/30',
              isActive && 'bg-primary/15 font-semibold text-primary',
              motionOk && 'transition-colors duration-150',
            )}
          >
            {letter}
          </button>
        )
      })}
    </div>
  )
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
 *
 * List view also carries an A-Z index rail (`AlphabetIndexRail`, PHASE-UI-EFFECTS-2.md §2
 * item 1): clicking a letter scrolls to that letter's section, and an `IntersectionObserver`
 * tracks which section is currently in view to highlight the matching letter. Chosen over the
 * research's native `view-timeline`/`animation-timeline` CSS approach because the character
 * count (and therefore section count/size) is fully dynamic per Book — `view-timeline` needs a
 * scroll range known/stable enough to bind to per named timeline, which fights a list that can
 * be 3 characters today and 300 after an import; `IntersectionObserver` degrades gracefully to
 * any length with the same code path. The highlight transition is the only thing gated by
 * `useDelight().motionOk` — the rail's buttons and jump behavior work identically regardless.
 */
export function CharactersPanel({ bookId }: { bookId: string }) {
  const [viewMode, setViewMode] = useState<CharactersViewMode>('list')
  const [query, setQuery] = useState('')
  const [editingEntry, setEditingEntry] = useState<CodexEntry | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newSummary, setNewSummary] = useState('')
  const [activeLetter, setActiveLetter] = useState<string | null>(null)
  const sectionRefs = useRef(new Map<string, HTMLElement>())
  const intersectingLettersRef = useRef(new Set<string>())
  const { motionOk } = useDelight()

  const [attachOpen, setAttachOpen] = useState(false)
  const [attachQuery, setAttachQuery] = useState('')

  const { data, isLoading } = useBookCharacters(bookId)
  const { data: books } = useBooks()
  const createCodex = useCreateCodex()
  const linkToBook = useLinkCodexToBook(bookId)

  // "Attach existing" (PHASE-UI-EFFECTS §3 gap fix): CodexEntry is canonical/shared across
  // every Book (no `book_id` column at all — association is via `book_codex_links`), so a
  // character created while working on a different Book has no UI anywhere to get attached
  // to *this* Book short of recreating it. `useCodexEntries('character')` already wraps the
  // unfiltered `GET /codex` (every character-type entry ever created, any Book) — reused as-is
  // rather than adding a new hook, same data `codex-panel.tsx` already fetches.
  const { data: allCharacters, isLoading: allCharactersLoading } = useCodexEntries('character')

  const entries = useMemo(() => data?.entries ?? [], [data])
  const relationships = useMemo(() => data?.relationships ?? [], [data])
  const filtered = useMemo(() => entries.filter((entry) => matchesQuery(entry, query)), [entries, query])

  // List-view-only alphabetized grouping (see class doc above) — built off `filtered`, so the
  // rail only ever offers/enables letters present among the current search results, never a
  // letter whose only matches are hidden by the query.
  const listGroups = useMemo(() => (viewMode === 'list' ? groupByLetter(filtered) : []), [filtered, viewMode])
  const availableLetters = useMemo(
    () => new Set(listGroups.map(([letter]) => letter).filter((letter) => letter !== '#')),
    [listGroups],
  )

  const setSectionRef = useCallback(
    (letter: string) => (el: HTMLElement | null) => {
      if (el) sectionRefs.current.set(letter, el)
      else sectionRefs.current.delete(letter)
    },
    [],
  )

  const jumpToLetter = useCallback(
    (letter: string) => {
      const el = sectionRefs.current.get(letter)
      el?.scrollIntoView({ behavior: motionOk ? 'smooth' : 'auto', block: 'start' })
    },
    [motionOk],
  )

  // Scrollspy: watches each letter-section heading and highlights whichever one is the
  // last (i.e. bottom-most, meaning most-recently-scrolled-past) section currently sitting in
  // the top band of the viewport. Recomputed from an accumulated intersecting-letters set
  // (not just the current callback's batch) so a letter doesn't lose highlight the instant its
  // own heading scrolls just out of the band while no other heading has entered it yet.
  useEffect(() => {
    intersectingLettersRef.current.clear()
    setActiveLetter(listGroups[0]?.[0] ?? null)
    if (viewMode !== 'list' || listGroups.length === 0) return

    const orderedLetters = listGroups.map(([letter]) => letter)

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const letter = (entry.target as HTMLElement).dataset.letterAnchor
          if (!letter) continue
          if (entry.isIntersecting) intersectingLettersRef.current.add(letter)
          else intersectingLettersRef.current.delete(letter)
        }
        let chosen: string | null = null
        for (const letter of orderedLetters) {
          if (intersectingLettersRef.current.has(letter)) chosen = letter
        }
        if (chosen) setActiveLetter(chosen)
      },
      // Top 30% of the viewport counts as "current" — a section heading is active from the
      // moment it crosses into that band until the next one does.
      { rootMargin: '0px 0px -70% 0px', threshold: 0 },
    )
    for (const el of sectionRefs.current.values()) observer.observe(el)
    return () => observer.disconnect()
  }, [listGroups, viewMode])

  // Already linked to this Book — excluded from the "Attach existing" picker so it only ever
  // offers characters not yet on this Book's list.
  const linkedIds = useMemo(() => new Set(entries.map((entry) => entry.id)), [entries])
  const attachCandidates = useMemo(
    () => (allCharacters ?? []).filter((entry) => !linkedIds.has(entry.id)),
    [allCharacters, linkedIds],
  )
  const filteredAttachCandidates = useMemo(
    () => attachCandidates.filter((entry) => matchesQuery(entry, attachQuery)),
    [attachCandidates, attachQuery],
  )

  function handleOpenAttach(open: boolean) {
    setAttachOpen(open)
    if (!open) setAttachQuery('')
  }

  function handleAttachExisting(entryId: string) {
    linkToBook.mutate(entryId)
  }

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

        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="outline" onClick={() => handleOpenAttach(true)}>
            <UserPlus className="size-4" />
            Attach existing
          </Button>
          <Button size="sm" onClick={() => setCreating((prev) => !prev)}>
            <Plus className="size-4" />
            Add character
          </Button>
        </div>
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
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1 space-y-6">
            {listGroups.map(([letter, groupEntries]) => (
              <div key={letter}>
                {/* The section "anchor" — an IntersectionObserver target and jump destination,
                    not just a label, so it's rendered even for the '#' bucket (no rail entry,
                    but still a valid scroll target if it were ever needed). */}
                <h3
                  ref={setSectionRef(letter)}
                  data-letter-anchor={letter}
                  className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground"
                  aria-hidden="true"
                >
                  {letter === '#' ? '#' : letter}
                </h3>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {groupEntries.map((entry) => (
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
              </div>
            ))}
          </div>
          <AlphabetIndexRail
            available={availableLetters}
            active={activeLetter}
            motionOk={motionOk}
            onJump={jumpToLetter}
          />
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

      <Dialog open={attachOpen} onOpenChange={handleOpenAttach}>
        <DialogContent className="max-w-md gap-4">
          <DialogHeader>
            <DialogTitle>Attach an existing character</DialogTitle>
            <DialogDescription>
              Characters are shared across your whole Story Library. Pick one already created
              in another Book to add it to this one.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor="attach-character-search">Search characters</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                id="attach-character-search"
                value={attachQuery}
                onChange={(event) => setAttachQuery(event.target.value)}
                placeholder="Filter by name or summary…"
                className="pl-8"
                autoComplete="off"
              />
            </div>
          </div>

          <ScrollArea className="h-[min(50vh,320px)]">
            {allCharactersLoading ? (
              <p className="flex items-center justify-center gap-2 px-1 py-6 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Loading characters…
              </p>
            ) : attachCandidates.length === 0 ? (
              <p className="px-1 py-6 text-center text-sm text-muted-foreground">
                Every character in your Story Library is already linked to this Book.
              </p>
            ) : filteredAttachCandidates.length === 0 ? (
              <p className="px-1 py-6 text-center text-sm text-muted-foreground">
                No characters match “{attachQuery.trim()}”.
              </p>
            ) : (
              <ul className="flex flex-col gap-1 pr-2">
                {filteredAttachCandidates.map((entry) => (
                  <li key={entry.id}>
                    <button
                      type="button"
                      onClick={() => handleAttachExisting(entry.id)}
                      disabled={linkToBook.isPending}
                      className={cn(
                        'flex w-full flex-col gap-0.5 rounded-lg border border-transparent px-3 py-2 text-left transition-colors',
                        'hover:bg-accent hover:text-accent-foreground',
                        'focus-visible:border-ring focus-visible:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                        'disabled:cursor-not-allowed disabled:opacity-60',
                      )}
                    >
                      <span className="truncate text-sm font-medium">{entry.name}</span>
                      {entry.summary && (
                        <span className="line-clamp-2 text-xs text-muted-foreground">{entry.summary}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookOpen, Drama, Loader2, Search, Users } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useSearch, type SearchResult } from '@/queries/search'
import { useBooks } from '@/queries/books'
import { cn } from '@/lib/utils'

const ENTITY_LABEL: Record<SearchResult['entity_type'], string> = {
  scene: 'Scene',
  codex_entry: 'Codex Entry',
}

const ENTITY_ICON: Record<SearchResult['entity_type'], typeof Drama> = {
  scene: Drama,
  codex_entry: Users,
}

/** Truncates a snippet to a sane display length — the backend's FTS5 snippet already trims
 * around the match, this is just a belt-and-suspenders cap for the rare long one. */
function truncateSnippet(snippet: string, max = 220): string {
  if (snippet.length <= max) return snippet
  return `${snippet.slice(0, max).trimEnd()}…`
}

/**
 * Global Story Library search (Phase 10 task 6, PHASE10.md) — a dialog with a debounced
 * search input (`useSearch`, `src/queries/search.ts`) and a ranked results list spanning
 * every canonical Scene/CodexEntry across the whole library, not one Book (docs/03,
 * PROJECT-MAP.md §1). Opened from `AppShell`'s sidebar search entry.
 *
 * Navigation decision: a result may be linked to more than one Book (`book_ids`), since
 * Scenes/CodexEntries are canonical and reusable. Rather than a Book-picker, clicking a
 * result always opens its *first* linked Book's canvas (`/book/:bookId`) — the simplest
 * option per the task's own "keep it simple" call. If it's linked to more than one Book,
 * the extra ones are still surfaced as chips so the user knows to look elsewhere if that
 * wasn't the right one. A result with no linked Book at all (not yet placed anywhere) is
 * shown but not clickable, with a note explaining why.
 *
 * Accessibility: the input has a real `<Label>` (visually present, not just a placeholder),
 * results are real `<button>`s so Tab already walks through them in order; ArrowUp/ArrowDown
 * additionally roves focus directly between the input and results for fast keyboard use,
 * and Enter on a focused result opens it (native button behavior). Loading/empty/result-count
 * states are announced via a visually-hidden `aria-live="polite"` status region, mirroring
 * `components/backup-nudge.tsx`'s `role="status"` pattern, in addition to the visible text.
 */
export function SearchDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const resultRefs = useRef<Array<HTMLButtonElement | null>>([])

  const { data: results, isLoading, isFetching, error } = useSearch(query)
  const { data: books } = useBooks()

  const bookTitleById = useMemo(() => {
    const map = new Map<string, string>()
    for (const book of books ?? []) map.set(book.id, book.title)
    return map
  }, [books])

  // Reset the query each time the dialog is reopened, so it never reopens mid-search from
  // last time.
  useEffect(() => {
    if (open) {
      setQuery('')
      resultRefs.current = []
      // Radix focuses the dialog content itself first; defer to land focus in the input.
      const id = window.setTimeout(() => inputRef.current?.focus(), 0)
      return () => window.clearTimeout(id)
    }
  }, [open])

  function openResult(result: SearchResult) {
    const bookId = result.book_ids[0]
    if (!bookId) return
    onOpenChange(false)
    navigate(`/book/${bookId}`)
  }

  function focusResult(index: number) {
    const clamped = Math.max(0, Math.min(index, (results?.length ?? 1) - 1))
    resultRefs.current[clamped]?.focus()
  }

  function handleInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && results && results.length > 0) {
      event.preventDefault()
      focusResult(0)
    }
  }

  function handleResultKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      focusResult(index + 1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (index === 0) {
        inputRef.current?.focus()
      } else {
        focusResult(index - 1)
      }
    }
  }

  const trimmedQuery = query.trim()
  const showEmpty = trimmedQuery.length > 0 && !isLoading && !isFetching && (results?.length ?? 0) === 0
  const statusText = trimmedQuery.length === 0
    ? 'Type to search Scenes and Codex entries.'
    : isLoading || isFetching
      ? 'Searching…'
      : error
        ? 'Search failed. Please try again.'
        : showEmpty
          ? `No results found for "${trimmedQuery}".`
          : `${results?.length ?? 0} result${results?.length === 1 ? '' : 's'} found.`

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl gap-4">
        <DialogHeader>
          <DialogTitle>Search the Story Library</DialogTitle>
          <DialogDescription>
            Find Scenes and Codex entries across every Book by keyword or meaning.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="library-search-input">Search Scenes and Codex entries</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="library-search-input"
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="Search by title, text, or meaning…"
              className="pl-8"
              autoComplete="off"
              role="combobox"
              aria-expanded={(results?.length ?? 0) > 0}
              aria-controls="library-search-results"
            />
          </div>
        </div>

        <div role="status" aria-live="polite" className="sr-only">
          {statusText}
        </div>

        <ScrollArea className="h-[min(60vh,420px)]" id="library-search-results">
          {trimmedQuery.length === 0 ? (
            <p className="px-1 py-6 text-center text-sm text-muted-foreground">{statusText}</p>
          ) : isLoading || (isFetching && (results?.length ?? 0) === 0) ? (
            <p className="flex items-center justify-center gap-2 px-1 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              Searching…
            </p>
          ) : showEmpty ? (
            <p className="px-1 py-6 text-center text-sm text-muted-foreground">
              No results found for &quot;{trimmedQuery}&quot;. Try a different word or phrasing.
            </p>
          ) : (
            <ul className="flex flex-col gap-1 pr-2">
              {results?.map((result, index) => {
                const Icon = ENTITY_ICON[result.entity_type]
                const bookId = result.book_ids[0]
                const extraBookCount = result.book_ids.length - 1
                const primaryBookTitle = bookId ? bookTitleById.get(bookId) : undefined

                return (
                  <li key={`${result.entity_type}-${result.entity_id}`}>
                    <button
                      ref={(el) => {
                        resultRefs.current[index] = el
                      }}
                      type="button"
                      onClick={() => openResult(result)}
                      onKeyDown={(event) => handleResultKeyDown(event, index)}
                      disabled={!bookId}
                      className={cn(
                        'flex w-full flex-col gap-1 rounded-lg border border-transparent px-3 py-2.5 text-left transition-colors',
                        'hover:bg-accent hover:text-accent-foreground',
                        'focus-visible:border-ring focus-visible:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                        'disabled:cursor-not-allowed disabled:opacity-60',
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                        <span className="min-w-0 flex-1 truncate text-sm font-medium">{result.title}</span>
                        <Badge variant={result.entity_type === 'scene' ? 'secondary' : 'outline'}>
                          {ENTITY_LABEL[result.entity_type]}
                        </Badge>
                      </div>
                      {result.snippet && (
                        <p className="line-clamp-2 text-xs text-muted-foreground">
                          {truncateSnippet(result.snippet)}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                        {bookId ? (
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <BookOpen className="size-3" aria-hidden="true" />
                            {primaryBookTitle ?? 'Untitled Book'}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">Not linked to a Book yet</span>
                        )}
                        {extraBookCount > 0 && (
                          <Badge variant="ghost" className="px-1.5 py-0 text-[10px] text-muted-foreground">
                            +{extraBookCount} more book{extraBookCount === 1 ? '' : 's'}
                          </Badge>
                        )}
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

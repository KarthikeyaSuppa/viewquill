import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Story Library search (Phase 10 task 6, PHASE10.md) — hybrid FTS5+vector search across
 * every canonical Scene/CodexEntry, not scoped to one Book (Scenes/CodexEntries are shared
 * across Books per docs/03-DATA-MODEL.md). `GET /search` isn't in the generated
 * `packages/api-types/schema.d.ts` yet (would need `npm run gen:types` against a running
 * sidecar) — this mirrors `src/queries/backups.ts`/`src/queries/canvas-templates.ts`'s
 * precedent of hand-declaring the shape locally rather than blocking on regeneration.
 * Matches the (stub-embedding-backed) `app/services/search_service.py` result shape.
 */

export type SearchEntityType = 'scene' | 'codex_entry'

export interface SearchResult {
  entity_type: SearchEntityType
  entity_id: string
  title: string
  snippet: string
  score: number
  /** Every Book this Scene/CodexEntry is currently linked to — may be empty (an entry not
   * yet placed on any canvas / not yet linked to a scene in any Book) or have more than one
   * entry, since Scenes/CodexEntries are canonical and reusable across Books. */
  book_ids: string[]
}

export interface UseSearchOptions {
  entityType?: SearchEntityType
  limit?: number
}

const DEBOUNCE_MS = 300

/** Debounces a fast-changing value — same discipline as the SSE-cancel/debounce guidance
 * in docs/04-LLM-INTEGRATION.md, applied here to keystrokes instead of a stream: the raw
 * `query` the input renders updates every keystroke, but the value actually sent to the
 * backend only settles `DEBOUNCE_MS` after the user stops typing, so we never fire a
 * request per keystroke. */
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])
  return debounced
}

/** `GET /search?q=...&limit=...&entity_type=...` (PHASE10.md task 4/6) — debounced so
 * typing doesn't fire a request per keystroke, and disabled entirely on an empty/whitespace
 * query so opening the search dialog doesn't immediately hit the backend. Keeps the
 * previous page's results visible (`placeholderData`) while a new debounced query is
 * in-flight, so the results list doesn't flash empty on every keystroke settle. */
export function useSearch(query: string, opts: UseSearchOptions = {}) {
  const { entityType, limit = 20 } = opts
  const trimmed = query.trim()
  const debouncedQuery = useDebouncedValue(trimmed, DEBOUNCE_MS)

  return useQuery({
    queryKey: ['search', debouncedQuery, entityType, limit],
    queryFn: () => {
      const params = new URLSearchParams({ q: debouncedQuery, limit: String(limit) })
      if (entityType) params.set('entity_type', entityType)
      return api.get<SearchResult[]>(`/search?${params.toString()}`)
    },
    enabled: debouncedQuery.length > 0,
    placeholderData: (prev) => prev,
  })
}

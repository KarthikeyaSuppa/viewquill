import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Scene suggestions (Phase 10 task 7, PHASE10.md) — read-only Codex-link and
 * similar-scene hints for the Scene currently open in the node editor drawer
 * (`components/canvas/node-editor.tsx`). `GET /search/scenes/{scene_id}/suggestions`
 * isn't in the generated `packages/api-types/schema.d.ts` yet — same hand-declared-shape
 * precedent as `queries/search.ts`/`queries/backups.ts`. Mirrors the exact field names in
 * `apps/sidecar/app/models/schemas.py`'s `CodexLinkSuggestion`/`SimilarSceneSuggestion`/
 * `SceneSuggestionsResponse`.
 *
 * These are suggestions only, never auto-applied (docs `PROJECT-MAP.md` §9's Accept/Reject
 * hard rule) — linking still goes through the existing `useLinkCodexToScene` mutation
 * (`queries/codex.ts`), and a similar-scene hint is purely informational.
 */

export interface CodexLinkSuggestion {
  codex_entry_id: string
  name: string
  snippet: string | null
  score: number
}

export interface SimilarSceneSuggestion {
  scene_id: string
  title: string
  snippet: string | null
  score: number
}

export interface SceneSuggestionsResponse {
  codex_link_suggestions: CodexLinkSuggestion[]
  similar_scenes: SimilarSceneSuggestion[]
}

/** Fetches both suggestion lists for one Scene, once per Scene-detail-view open (not on
 * every keystroke — there's nothing to type here). Keyed by `sceneId` so switching which
 * node is open in the drawer (`key={sceneId}` in `NodeEditor`) fetches fresh suggestions
 * for the newly-opened scene rather than reusing the previous scene's cached list. */
export function useSceneSuggestions(sceneId: string | undefined) {
  return useQuery({
    queryKey: ['scene-suggestions', sceneId],
    queryFn: () => api.get<SceneSuggestionsResponse>(`/search/scenes/${sceneId}/suggestions`),
    enabled: !!sceneId,
  })
}

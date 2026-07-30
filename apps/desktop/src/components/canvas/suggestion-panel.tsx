import { useState } from 'react'
import { Link2, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useSceneSuggestions } from '@/queries/suggestions'
import { useLinkCodexToScene, useSceneCodex } from '@/queries/codex'

/**
 * Suggestion surface for one Scene's node-editor drawer (Phase 10 task 7, PHASE10.md) —
 * shows the two read-only lists `GET /search/scenes/{scene_id}/suggestions` returns:
 * Codex entries this scene might want linked, and other Scenes it resembles.
 *
 * Hard rule (`PROJECT-MAP.md` §9 — every AI-adjacent transform is Accept/Reject, never
 * silently applied): nothing here writes anything on its own. The Codex list only offers a
 * "Link" button that calls the *existing* `useLinkCodexToScene` mutation
 * (`queries/codex.ts`, the same one `codex-panel.tsx`'s link toggle uses) — there's no
 * second, parallel link-creation path. The similar-scenes list has no action at all, it's
 * pure awareness. Dismissing a suggestion only hides it for this open drawer (local
 * component state) — there's no "don't suggest again" backend state, out of scope per
 * PHASE10.md task 7.
 *
 * Copy is deliberately hedged ("Possible match based on shared text/wording") rather than
 * "AI found this" — on this machine the embedding is a deterministic stub with no semantic
 * meaning yet (real `qwen3-embedding` lands on the target machine per PHASE10.md §3), and
 * even once it does this is still a ranked guess a person must accept, not a fact.
 */
export function SuggestionPanel({ sceneId }: { sceneId: string }) {
  const { data, isLoading, isError } = useSceneSuggestions(sceneId)
  const { data: linkedEntries } = useSceneCodex(sceneId)
  const linkToScene = useLinkCodexToScene(sceneId)

  const [dismissedCodex, setDismissedCodex] = useState<Set<string>>(new Set())
  const [dismissedScenes, setDismissedScenes] = useState<Set<string>>(new Set())

  const linkedIds = new Set((linkedEntries ?? []).map((entry) => entry.id))
  const codexSuggestions = (data?.codex_link_suggestions ?? []).filter(
    (s) => !dismissedCodex.has(s.codex_entry_id) && !linkedIds.has(s.codex_entry_id),
  )
  const similarScenes = (data?.similar_scenes ?? []).filter(
    (s) => !dismissedScenes.has(s.scene_id),
  )

  if (isLoading) {
    return (
      <p className="text-xs text-muted-foreground" role="status" aria-live="polite">
        Checking for suggestions…
      </p>
    )
  }

  // A failed suggestion fetch is never worth blocking the rest of the drawer over —
  // scene editing works fine without it, so this section just quietly disappears.
  if (isError || (codexSuggestions.length === 0 && similarScenes.length === 0)) {
    return null
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-dashed border-border p-3">
      {codexSuggestions.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <Badge variant="outline">Suggested</Badge>
            <p className="text-xs font-medium">You might want to link:</p>
          </div>
          <ul className="flex flex-col gap-1.5">
            {codexSuggestions.map((suggestion) => (
              <li
                key={suggestion.codex_entry_id}
                className="flex items-start justify-between gap-2 rounded-md bg-muted/50 px-2 py-1.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{suggestion.name}</p>
                  {suggestion.snippet && (
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {suggestion.snippet}
                    </p>
                  )}
                  <p className="text-[11px] text-muted-foreground">
                    Possible match based on shared text
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    size="sm"
                    variant="secondary"
                    className="h-7 px-2 text-xs"
                    onClick={() => linkToScene.mutate(suggestion.codex_entry_id)}
                    disabled={linkToScene.isPending}
                    aria-label={`Link ${suggestion.name} to this scene`}
                  >
                    <Link2 className="size-3" />
                    Link
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    aria-label={`Dismiss suggestion to link ${suggestion.name}`}
                    onClick={() =>
                      setDismissedCodex((prev) => new Set(prev).add(suggestion.codex_entry_id))
                    }
                  >
                    <X className="size-3.5" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {similarScenes.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-1.5">
            <Badge variant="outline">Suggested</Badge>
            <p className="text-xs font-medium">This looks similar to:</p>
          </div>
          <ul className="flex flex-col gap-1.5">
            {similarScenes.map((suggestion) => (
              <li
                key={suggestion.scene_id}
                className="flex items-start justify-between gap-2 rounded-md bg-muted/50 px-2 py-1.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{suggestion.title}</p>
                  {suggestion.snippet && (
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {suggestion.snippet}
                    </p>
                  )}
                  <p className="text-[11px] text-muted-foreground">
                    Possible match based on shared text
                  </p>
                </div>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`Dismiss similar scene ${suggestion.title}`}
                  onClick={() =>
                    setDismissedScenes((prev) => new Set(prev).add(suggestion.scene_id))
                  }
                >
                  <X className="size-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

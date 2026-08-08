import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  useCodexEntries,
  useCreateCodex,
  useLinkCodexToScene,
  useSceneCodex,
  useUnlinkCodexFromScene,
} from '@/queries/codex'
import { useBooks } from '@/queries/books'
import { imageThumbUrl } from '@/queries/images'
import { CodexEntryDialog } from '@/components/codex/codex-entry-dialog'
import type { CodexEntry } from '@/lib/api'
import { useSliceDelete } from '@/components/ui/slice-delete'
import { cn } from '@/lib/utils'

function initialsFor(name: string): string {
  return name.trim().slice(0, 3).toUpperCase() || '?'
}

/**
 * The node editor's own character rail (docs PHASE13 Workstream C task C5) — distinct
 * from the canvas-wide `codex-panel.tsx` left drawer (that one lists/filters/links ANY
 * Codex type against whichever node happens to be selected on canvas; this one lives
 * inside the drawer itself, scoped to exactly the scene currently open, characters only,
 * with no type filter to fall back on). Circular chips reuse that panel's visual language
 * (image-or-initials circle, full `CodexEntryDialog` on click) but add a per-chip hover
 * unlink (✕) and a dedicated "Add character" picker/create flow of its own.
 *
 * Unlink only ever removes the Scene↔Codex link (`useUnlinkCodexFromScene`) — the
 * character entry itself, and any other Scene/Book it's linked to, is untouched. Nothing
 * here deletes a Codex entry.
 */
export function SceneCharactersSection({ sceneId }: { sceneId: string | undefined }) {
  const [editingEntry, setEditingEntry] = useState<CodexEntry | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)

  const { data: books } = useBooks()
  const { data: linked } = useSceneCodex(sceneId)
  const { data: allCharacters } = useCodexEntries('character')
  const linkToScene = useLinkCodexToScene(sceneId)
  const unlinkFromScene = useUnlinkCodexFromScene(sceneId)
  const createCodex = useCreateCodex()

  if (!sceneId) return null

  const characters = (linked ?? []).filter((entry) => entry.entry_type === 'character')
  const linkedIds = new Set(characters.map((entry) => entry.id))
  const pickable = (allCharacters ?? []).filter((entry) => !linkedIds.has(entry.id))

  function handlePick(entryId: string) {
    linkToScene.mutate(entryId)
    setPickerOpen(false)
  }

  /** Creates a bare "New character" entry, links it to this Scene immediately, closes the
   * picker, and opens the full `CodexEntryDialog` so the user can name/detail it right
   * away — same create-then-edit flow `codex-panel.tsx`'s `handleCreate` already uses. */
  function handleCreateNew() {
    createCodex.mutate(
      { entry_type: 'character', name: 'New character' },
      {
        onSuccess: (created) => {
          linkToScene.mutate(created.id)
          setPickerOpen(false)
          setEditingEntry(created)
        },
      },
    )
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Label>Characters</Label>
      <div className="flex flex-wrap gap-2">
        {characters.map((entry) => (
          <CharacterChip
            key={entry.id}
            entry={entry}
            onOpen={() => setEditingEntry(entry)}
            onUnlink={() => unlinkFromScene.mutate(entry.id)}
            unlinkPending={unlinkFromScene.isPending}
          />
        ))}

        <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
          <Tooltip>
            <TooltipTrigger asChild>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  aria-label="Add character to this scene"
                  className="flex size-12 shrink-0 items-center justify-center rounded-full border-2 border-dashed border-border text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
                >
                  <Plus className="size-4" />
                </button>
              </PopoverTrigger>
            </TooltipTrigger>
            <TooltipContent>Add character</TooltipContent>
          </Tooltip>
          <PopoverContent align="start" className="w-64 p-2">
            <p className="mb-1.5 px-1 text-xs font-semibold text-muted-foreground">Link a character</p>
            {pickable.length === 0 ? (
              <p className="px-1 py-1 text-xs text-muted-foreground">No other characters to add yet.</p>
            ) : (
              <ScrollArea className="max-h-48">
                <div className="flex flex-col gap-0.5">
                  {pickable.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => handlePick(entry.id)}
                      disabled={linkToScene.isPending}
                      className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
                    >
                      <span className="flex size-6 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted text-[9px] font-semibold text-muted-foreground">
                        {entry.primary_image_id ? (
                          <img
                            src={imageThumbUrl(entry.primary_image_id)}
                            alt=""
                            className="size-full object-cover"
                          />
                        ) : (
                          initialsFor(entry.name)
                        )}
                      </span>
                      <span className="truncate">{entry.name}</span>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            )}
            <div className="mt-1.5 border-t border-border pt-1.5">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="w-full justify-start gap-1.5 text-xs"
                onClick={handleCreateNew}
                disabled={createCodex.isPending}
              >
                <Plus className="size-3.5" />
                Create new character
              </Button>
            </div>
          </PopoverContent>
        </Popover>
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

/** One linked character as a circular chip — image thumbnail (or initials) in a circle,
 * a tooltip with the full name, and a hover/focus-revealed unlink (✕). Clicking the
 * circle itself opens the full `CodexEntryDialog`. */
function CharacterChip({
  entry,
  onOpen,
  onUnlink,
  unlinkPending,
}: {
  entry: CodexEntry
  onOpen: () => void
  onUnlink: () => void
  unlinkPending: boolean
}) {
  // Slice-to-delete removal (Playful + motion only, instant everywhere else — see
  // `components/ui/slice-delete.tsx`). `onUnlink` (→ `useUnlinkCodexFromScene`) is
  // unchanged and always fires; this only delays the chip's visual unmount.
  const sliceDelete = useSliceDelete(onUnlink, 'chip')

  return (
    <div className={cn('group relative', sliceDelete.className)} onAnimationEnd={sliceDelete.onAnimationEnd}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onOpen}
            aria-label={`Open “${entry.name}”`}
            className="flex size-12 items-center justify-center overflow-hidden rounded-full border-2 border-border bg-muted text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:outline-none"
          >
            {entry.primary_image_id ? (
              <img src={imageThumbUrl(entry.primary_image_id)} alt="" className="size-full object-cover" />
            ) : (
              initialsFor(entry.name)
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent>{entry.name}</TooltipContent>
      </Tooltip>
      <button
        type="button"
        aria-label={`Remove “${entry.name}” from this scene`}
        onClick={(event) => {
          event.stopPropagation()
          sliceDelete.startRemove()
        }}
        disabled={unlinkPending}
        className="absolute -top-1 -right-1 rounded-full bg-background p-0.5 opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100 disabled:pointer-events-none"
      >
        <X className="size-3" />
      </button>
    </div>
  )
}

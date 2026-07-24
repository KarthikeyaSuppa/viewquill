import { useState, type FormEvent } from 'react'
import { Plus, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAddTag, useRemoveTag } from '@/queries/images'

/**
 * Add/remove tags on one image (docs/06 Phase 5 task FE-A). Embedded in `image-card.tsx`'s
 * "Manage tags" dialog — not a standalone route.
 */
export function TagEditor({ imageId, tags }: { imageId: string; tags: string[] }) {
  const [draft, setDraft] = useState('')
  const addTag = useAddTag()
  const removeTag = useRemoveTag()

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed || tags.includes(trimmed)) return
    addTag.mutate({ id: imageId, tag: trimmed }, { onSuccess: () => setDraft('') })
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        {tags.length === 0 ? (
          <p className="text-xs text-muted-foreground">No tags yet.</p>
        ) : (
          tags.map((tag) => (
            <Badge key={tag} variant="secondary" className="gap-1 pr-1">
              {tag}
              <button
                type="button"
                aria-label={`Remove tag ${tag}`}
                className="rounded-full p-0.5 hover:bg-background/60"
                onClick={() => removeTag.mutate({ id: imageId, tag })}
                disabled={removeTag.isPending}
              >
                <X className="size-3" />
              </button>
            </Badge>
          ))
        )}
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          aria-label="New tag"
          placeholder="Add a tag…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={addTag.isPending}
        />
        <Button type="submit" size="sm" disabled={!draft.trim() || addTag.isPending}>
          <Plus className="size-3.5" />
          Add
        </Button>
      </form>
    </div>
  )
}

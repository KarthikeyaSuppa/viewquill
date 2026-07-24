import { useEffect, useState } from 'react'
import { ImagePlus, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { TagEditor } from '@/components/images/tag-editor'
import { EnhanceDiff } from '@/components/canvas/enhance-diff'
import { acceptLog, useEnhance } from '@/queries/enhance'
import { imageUrl, useUpdateImage } from '@/queries/images'
import { useUpdateBook } from '@/queries/books'
import type { ImageRead } from '@/lib/api'

/**
 * The image detail dialog (docs/06 Phase 5 task FE-B) — opened from an `ImageCard` click.
 * Shows the full image, an editable name, the shared `TagEditor`, and a Description field
 * whose Enhance ✨ flow is a literal clone of `node-editor.tsx`'s prose Description block:
 * `useEnhance()` only ever streams a suggestion into local state, `<EnhanceDiff/>` renders
 * the review, and Accept is the *sole* path that PATCHes the real Image (via
 * `useUpdateImage`) — Reject (or a plain manual edit + "Save description") never goes
 * through Enhance's accept-log at all. `bookId`, when given (i.e. this dialog was opened
 * from a Book's Images tab), also offers "Set as book cover" — a plain `useUpdateBook`
 * PATCH of `cover_image_id`, nothing export/import-related.
 */
export function ImageDetail({
  image,
  open,
  onOpenChange,
  bookId,
}: {
  image: ImageRead
  open: boolean
  onOpenChange: (open: boolean) => void
  bookId?: string
}) {
  const updateImage = useUpdateImage()
  const updateBook = useUpdateBook()
  const enhance = useEnhance()
  const [reviewing, setReviewing] = useState(false)

  const [displayName, setDisplayName] = useState(image.display_name)
  const [description, setDescription] = useState(image.description ?? '')

  // Reset local drafts whenever a *different* image is opened, or the dialog is
  // (re)opened for the same image — never clobber an in-progress edit just because the
  // images query refetched in the background while the dialog stayed open.
  useEffect(() => {
    if (!open) return
    setDisplayName(image.display_name)
    setDescription(image.description ?? '')
    setReviewing(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, image.id])

  const nameDirty = displayName.trim().length > 0 && displayName.trim() !== image.display_name
  const descriptionDirty = description !== (image.description ?? '')

  function handleSaveName() {
    if (!nameDirty) return
    updateImage.mutate({ id: image.id, display_name: displayName.trim() })
  }

  function handleSaveDescription() {
    if (!descriptionDirty) return
    updateImage.mutate({ id: image.id, description: description.trim() === '' ? null : description })
  }

  function handleEnhanceClick() {
    setReviewing(true)
    enhance.start({
      mode: 'prose',
      text: description,
      field: 'description',
      entity_type: 'image',
      entity_id: image.id,
    })
  }

  // The ONLY writer: takes the (possibly hand-edited) suggestion text and PATCHes the
  // canonical Image. Never called from Reject.
  function handleAccept(finalText: string) {
    setDescription(finalText)
    updateImage.mutate({ id: image.id, description: finalText })
    if (enhance.logId) acceptLog(enhance.logId, true)
    setReviewing(false)
  }

  // Writes NOTHING — `description` (both local state and the saved Image) is untouched.
  function handleReject() {
    if (enhance.logId) acceptLog(enhance.logId, false)
    setReviewing(false)
  }

  function handleSetCover() {
    if (!bookId) return
    updateBook.mutate({ id: bookId, cover_image_id: image.id })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Image details</DialogTitle>
        </DialogHeader>

        <img
          src={imageUrl(image.id)}
          alt={image.display_name}
          className="max-h-[45vh] w-full rounded-xl bg-muted object-contain"
        />

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="image-detail-name">Name</Label>
          <div className="flex gap-2">
            <Input
              id="image-detail-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
            <Button size="sm" onClick={handleSaveName} disabled={!nameDirty || updateImage.isPending}>
              Save
            </Button>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Tags</Label>
          <TagEditor imageId={image.id} tags={image.tags} />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="image-detail-description">Description</Label>
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleEnhanceClick}
                    disabled={enhance.isStreaming || description.trim().length === 0}
                    className="gap-1 text-xs"
                  >
                    <Sparkles className="size-3.5" />
                    Enhance
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>Expand & improve — you review before anything is saved</TooltipContent>
            </Tooltip>
          </div>
          <Textarea
            id="image-detail-description"
            className="manuscript min-h-24"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Describe this image…"
          />

          {reviewing && (
            <EnhanceDiff
              original={description}
              enhanced={enhance.streamedText}
              provider={enhance.provider}
              isStreaming={enhance.isStreaming}
              acceptPending={updateImage.isPending}
              onAccept={handleAccept}
              onReject={handleReject}
            />
          )}
          {enhance.error && <p className="text-xs text-destructive">Enhance failed: {enhance.error}</p>}

          {!reviewing && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleSaveDescription}
              disabled={!descriptionDirty || updateImage.isPending}
              className="self-start"
            >
              Save description
            </Button>
          )}
        </div>

        {bookId && (
          <DialogFooter className="sm:justify-start">
            <Button
              variant="outline"
              onClick={handleSetCover}
              disabled={updateBook.isPending}
              className="gap-1"
            >
              <ImagePlus className="size-3.5" />
              Set as book cover
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

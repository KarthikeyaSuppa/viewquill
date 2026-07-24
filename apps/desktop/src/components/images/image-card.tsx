import { useEffect, useState, type FormEvent } from 'react'
import { EllipsisVertical, ImagePlus, Pencil, Tags, Trash2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { imageThumbUrl } from '@/queries/images'
import { useDeleteImage, useUpdateImage } from '@/queries/images'
import { useUpdateBook } from '@/queries/books'
import { TagEditor } from '@/components/images/tag-editor'
import { ImageDetail } from '@/components/images/image-detail'
import type { ImageRead } from '@/lib/api'

/**
 * One image's thumbnail card in the gallery grid (docs/06 Phase 5 tasks FE-A/FE-B).
 * Clicking the card opens the `<ImageDetail/>` dialog (full image, rename, tags,
 * Enhance-able description, "set as book cover"). `readOnly` drops the quick-actions menu
 * entirely — used by the "In this Book" export-preview view, which must never let a user
 * think they're editing the export itself (it's a read-only join over whatever's actually
 * attached) — the detail dialog it opens stays fully editable regardless, same as clicking
 * into any other image.  `bookId`, when given, is threaded through to `<ImageDetail/>` and
 * this card's own "Set as cover" menu item so `cover_image_id` can be PATCHed.
 */
export function ImageCard({
  image,
  readOnly = false,
  bookId,
}: {
  image: ImageRead
  readOnly?: boolean
  bookId?: string
}) {
  const [renameOpen, setRenameOpen] = useState(false)
  const [tagsOpen, setTagsOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const updateBook = useUpdateBook()

  return (
    <>
      <Card
        role="button"
        tabIndex={0}
        aria-label={`Open “${image.display_name}” details`}
        onClick={() => setDetailOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setDetailOpen(true)
          }
        }}
        className="glass glass-edge cursor-pointer gap-2 rounded-2xl border-0 p-2.5 shadow-none"
      >
        <div className="relative aspect-square overflow-hidden rounded-xl bg-muted">
          <img
            src={imageThumbUrl(image.id)}
            alt={image.display_name}
            className="size-full object-cover"
            loading="lazy"
          />
          {!readOnly && (
            <div className="absolute top-1.5 right-1.5" onClick={(event) => event.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="secondary"
                    size="icon-sm"
                    className="size-7 shadow-sm"
                    aria-label="Image actions"
                  >
                    <EllipsisVertical className="size-3.5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                    <Pencil />
                    Rename
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => setTagsOpen(true)}>
                    <Tags />
                    Manage tags
                  </DropdownMenuItem>
                  {bookId && (
                    <DropdownMenuItem
                      disabled={updateBook.isPending}
                      onSelect={() => updateBook.mutate({ id: bookId, cover_image_id: image.id })}
                    >
                      <ImagePlus />
                      Set as book cover
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => setDeleteOpen(true)}>
                    <Trash2 />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1 px-0.5">
          <p className="truncate text-xs font-medium" title={image.display_name}>
            {image.display_name}
          </p>
          {image.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {image.tags.slice(0, 3).map((tag) => (
                <Badge key={tag} variant="outline" className="text-[10px]">
                  {tag}
                </Badge>
              ))}
              {image.tags.length > 3 && (
                <Badge variant="outline" className="text-[10px]">
                  +{image.tags.length - 3}
                </Badge>
              )}
            </div>
          )}
        </div>
      </Card>

      <ImageDetail image={image} open={detailOpen} onOpenChange={setDetailOpen} bookId={bookId} />

      {!readOnly && (
        <>
          <RenameDialog image={image} open={renameOpen} onOpenChange={setRenameOpen} />
          <TagsDialog image={image} open={tagsOpen} onOpenChange={setTagsOpen} />
          <DeleteAlert image={image} open={deleteOpen} onOpenChange={setDeleteOpen} />
        </>
      )}
    </>
  )
}

function RenameDialog({
  image,
  open,
  onOpenChange,
}: {
  image: ImageRead
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const updateImage = useUpdateImage()
  const [displayName, setDisplayName] = useState(image.display_name)

  useEffect(() => {
    if (open) setDisplayName(image.display_name)
  }, [open, image.display_name])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = displayName.trim()
    if (!trimmed) return
    updateImage.mutate(
      { id: image.id, display_name: trimmed },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename image</DialogTitle>
          <DialogDescription>Give “{image.display_name}” a new name.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="rename-image-name">Name</Label>
            <Input
              id="rename-image-name"
              autoFocus
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={updateImage.isPending || !displayName.trim()}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function TagsDialog({
  image,
  open,
  onOpenChange,
}: {
  image: ImageRead
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Manage tags</DialogTitle>
          <DialogDescription>Tags help you find “{image.display_name}” later.</DialogDescription>
        </DialogHeader>
        <TagEditor imageId={image.id} tags={image.tags} />
      </DialogContent>
    </Dialog>
  )
}

function DeleteAlert({
  image,
  open,
  onOpenChange,
}: {
  image: ImageRead
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const deleteImage = useDeleteImage()

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{image.display_name}”?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the image and any tags/links to it. This can’t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={deleteImage.isPending}
            onClick={(e) => {
              e.preventDefault()
              deleteImage.mutate(image.id, { onSuccess: () => onOpenChange(false) })
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

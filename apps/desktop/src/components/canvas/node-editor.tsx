import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Dialog as DialogPrimitive } from 'radix-ui'
import { ArrowDown, ArrowUp, ImagePlus, Plus, Sparkles, Star, Trash2, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useRemoveFromCanvas, useUpdateScene } from '@/queries/canvas'
import {
  useCreateElement,
  useDeleteElement,
  useDeleteScene,
  useElements,
  useReorderElements,
  useUpdateElement,
  type ScreenplayElement,
  type ScreenplayElementType,
} from '@/queries/screenplay'
import { showUndoToast, useRedoLastAction, useUndoLastAction } from '@/queries/undo'
import { acceptLog, useEnhance } from '@/queries/enhance'
import {
  imageThumbUrl,
  useAttachImage,
  useDetachImage,
  useEntityImages,
  useImages,
  useReorderEntityImages,
  useUploadImage,
} from '@/queries/images'
import type { BookType } from '@/queries/books'
import type { SceneFlowNode } from '@/components/canvas/nodes'
import { EnhanceDiff } from '@/components/canvas/enhance-diff'
import { insertAtCaret, MicButton } from '@/components/voice/mic-button'

const STATUS_OPTIONS = ['draft', 'revised', 'final'] as const

const ELEMENT_TYPE_LABELS: Record<ScreenplayElementType, string> = {
  scene_heading: 'Scene Heading',
  action: 'Action',
  character: 'Character',
  dialogue: 'Dialogue',
  parenthetical: 'Parenthetical',
  transition: 'Transition',
  shot: 'Shot',
  dual_dialogue: 'Dual Dialogue',
}

const ELEMENT_TYPES = Object.keys(ELEMENT_TYPE_LABELS) as ScreenplayElementType[]

function isScriptBook(bookType: BookType | undefined): boolean {
  return bookType === 'movie_script' || bookType === 'short_film_script'
}

export interface NodeEditorProps {
  bookId: string
  bookType: BookType | undefined
  node: SceneFlowNode | null
  onClose: () => void
}

/** The right-side glass drawer opened from a canvas node click (docs/06 Phase 2 task G5).
 * Title/status are shared editable fields; the body switches between a prose Description
 * (story_book/single_scene) and a structured screenplay-elements editor (movie_script/
 * short_film_script). The footer keeps "unlink from canvas" and "delete forever" visually
 * and textually distinct — these do very different, non-reversible-in-one-case things. */
export function NodeEditor({ bookId, bookType, node, onClose }: NodeEditorProps) {
  const open = node !== null
  const sceneId = node?.data.sceneId
  const script = isScriptBook(bookType)

  const updateScene = useUpdateScene(bookId)
  const removeFromCanvas = useRemoveFromCanvas(bookId)
  const deleteScene = useDeleteScene()
  const undoLastAction = useUndoLastAction(bookId)
  const redoLastAction = useRedoLastAction(bookId)

  const [title, setTitle] = useState('')
  const [status, setStatus] = useState<string>('draft')
  const [description, setDescription] = useState('')

  // Reset local drafts only when a *different* node is opened — never clobber an
  // in-progress edit just because the canvas query refetched in the background.
  useEffect(() => {
    if (!node) return
    setTitle(node.data.title)
    setStatus(node.data.status ?? 'draft')
    setDescription(node.data.description ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node?.data.sceneId])

  const titleInvalid = title.trim().length === 0

  function handleSave() {
    if (!sceneId || titleInvalid) return
    updateScene.mutate({
      id: sceneId,
      title: title.trim(),
      status,
      ...(script ? {} : { description }),
    })
  }

  function handleRemoveFromCanvas() {
    if (!sceneId) return
    removeFromCanvas.mutate(sceneId, { onSuccess: () => onClose() })
  }

  function handleDeletePermanently() {
    if (!sceneId) return
    deleteScene.mutate(sceneId, {
      onSuccess: () => {
        onClose()
        showUndoToast(
          'Scene deleted permanently',
          () => undoLastAction.mutate(),
          () => redoLastAction.mutate(),
        )
      },
    })
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className={cn(
            'glass fixed inset-y-0 right-0 z-50 flex h-full w-full max-w-md flex-col gap-0 border-l border-border shadow-2xl outline-none',
            'data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:animate-in data-[state=open]:slide-in-from-right',
          )}
        >
          {sceneId ? (
            <NodeEditorBody
              key={sceneId}
              sceneId={sceneId}
              bookId={bookId}
              script={script}
              title={title}
              setTitle={setTitle}
              titleInvalid={titleInvalid}
              status={status}
              setStatus={setStatus}
              description={description}
              setDescription={setDescription}
              onSave={handleSave}
              savePending={updateScene.isPending}
              onRemoveFromCanvas={handleRemoveFromCanvas}
              removePending={removeFromCanvas.isPending}
              onDeletePermanently={handleDeletePermanently}
              deletePending={deleteScene.isPending}
            />
          ) : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

interface NodeEditorBodyProps {
  sceneId: string
  bookId: string
  script: boolean
  title: string
  setTitle: (value: string) => void
  titleInvalid: boolean
  status: string
  setStatus: (value: string) => void
  description: string
  setDescription: (value: string) => void
  onSave: () => void
  savePending: boolean
  onRemoveFromCanvas: () => void
  removePending: boolean
  onDeletePermanently: () => void
  deletePending: boolean
}

function NodeEditorBody({
  sceneId,
  bookId,
  script,
  title,
  setTitle,
  titleInvalid,
  status,
  setStatus,
  description,
  setDescription,
  onSave,
  savePending,
  onRemoveFromCanvas,
  removePending,
  onDeletePermanently,
  deletePending,
}: NodeEditorBodyProps) {
  const titleFieldRef = useRef<HTMLInputElement | null>(null)

  return (
    <>
      <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-4">
        <DialogPrimitive.Title className="text-sm font-semibold">Edit node</DialogPrimitive.Title>
        <DialogPrimitive.Close asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Close">
            <X className="size-4" />
          </Button>
        </DialogPrimitive.Close>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        <div className="flex flex-col gap-5 px-5 py-5">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="node-title">Title</Label>
              <MicButton
                fieldRef={titleFieldRef}
                label="Title"
                onTranscript={(text) => setTitle(insertAtCaret(titleFieldRef.current, title, text))}
              />
            </div>
            <Input
              id="node-title"
              ref={titleFieldRef}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              aria-invalid={titleInvalid}
              placeholder="Untitled"
            />
            {titleInvalid && <p className="text-xs text-destructive">Title can’t be empty.</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="node-status">Status</Label>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger id="node-status" className="w-full">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option[0].toUpperCase() + option.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {script ? (
            <ElementsEditor sceneId={sceneId} />
          ) : (
            <DescriptionField
              sceneId={sceneId}
              bookId={bookId}
              description={description}
              setDescription={setDescription}
            />
          )}

          <SceneImagesSection sceneId={sceneId} />

          <Button onClick={onSave} disabled={titleInvalid || savePending} className="self-start">
            {savePending ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </ScrollArea>

      <Separator />

      <div className="flex flex-col gap-3 px-5 py-4">
        <div className="flex flex-col gap-1">
          <Button
            variant="outline"
            onClick={onRemoveFromCanvas}
            disabled={removePending}
            className="justify-start"
          >
            Remove from canvas
          </Button>
          <p className="text-xs text-muted-foreground">
            Only unlinks this scene from this canvas — it stays in the Library and on any
            other Book it's linked to.
          </p>
        </div>

        <div className="flex flex-col gap-1">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={deletePending} className="justify-start">
                <Trash2 />
                Delete scene permanently
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete this scene forever?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes the scene — its title, description, and (for
                  screenplay scenes) every element in it — everywhere it appears, including
                  every other Book it's linked to. This can be undone via Undo, but only
                  briefly — after that it's gone for good. If you only want to remove it
                  from this canvas, use “Remove from canvas” instead.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction variant="destructive" onClick={onDeletePermanently}>
                  Delete permanently
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <p className="text-xs text-muted-foreground">
            Deletes the scene forever, everywhere it's used. Cannot be undone.
          </p>
        </div>
      </div>
    </>
  )
}

/** Prose-book body: the Description Textarea plus a real Enhance ✨ (docs/06 Phase 2 task
 * H2). Enhance only ever streams a *suggestion* into local state — Accept is the sole
 * path that writes it into the canonical Scene (via `useUpdateScene`); Reject (or
 * dismissing the panel) leaves `description` exactly as the user left it. */
function DescriptionField({
  sceneId,
  bookId,
  description,
  setDescription,
}: {
  sceneId: string
  bookId: string
  description: string
  setDescription: (value: string) => void
}) {
  const updateScene = useUpdateScene(bookId)
  const enhance = useEnhance()
  const [reviewing, setReviewing] = useState(false)
  const descriptionFieldRef = useRef<HTMLTextAreaElement | null>(null)

  function handleEnhanceClick() {
    setReviewing(true)
    enhance.start({
      mode: 'grammar',
      text: description,
      scene_id: sceneId,
      book_id: bookId,
      field: 'description',
      entity_type: 'scene',
      entity_id: sceneId,
    })
  }

  // The ONLY writer: takes the (possibly hand-edited) suggestion text and PATCHes the
  // canonical Scene. Never called from Reject.
  function handleAccept(finalText: string) {
    setDescription(finalText)
    updateScene.mutate({ id: sceneId, description: finalText })
    if (enhance.logId) acceptLog(enhance.logId, true)
    setReviewing(false)
  }

  // Writes NOTHING — `description` (both local state and the saved Scene) is untouched.
  function handleReject() {
    if (enhance.logId) acceptLog(enhance.logId, false)
    setReviewing(false)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor="node-description">Description</Label>
        <div className="flex items-center gap-1">
          <MicButton
            fieldRef={descriptionFieldRef}
            label="Description"
            onTranscript={(text) =>
              setDescription(insertAtCaret(descriptionFieldRef.current, description, text))
            }
          />
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
            <TooltipContent>Grammar & clarity pass — you review before anything is saved</TooltipContent>
          </Tooltip>
        </div>
      </div>
      <Textarea
        id="node-description"
        ref={descriptionFieldRef}
        className="manuscript min-h-32"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        placeholder="What happens here?"
      />
      {reviewing && (
        <EnhanceDiff
          original={description}
          enhanced={enhance.streamedText}
          provider={enhance.provider}
          isStreaming={enhance.isStreaming}
          acceptPending={updateScene.isPending}
          onAccept={handleAccept}
          onReject={handleReject}
        />
      )}
      {enhance.error && (
        <p className="text-xs text-destructive">Enhance failed: {enhance.error}</p>
      )}
    </div>
  )
}

/** Prose-book body: attach/detach/reorder finalized images on this scene (docs/06 Phase 5
 * task FE-B; reorder + "Make cover" added per `PHASE-UI-EFFECTS-2.md` §4 B2). A node here IS
 * a scene, so the node's `sceneId` is used directly as `entity_id`/`entity_type: 'scene'` for
 * the polymorphic `entity_images` link — no separate lookup needed. Two ways in: upload a
 * brand-new `finalized_scene` image (attaches it the moment the upload succeeds), or pick one
 * already sitting in the finalized_scene pool (e.g. one exported from the Images tab's
 * "Reference pool" earlier). Detach (✕) only ever removes the link — the image itself, and
 * any other entity it's attached to, is untouched.
 *
 * Reorder uses up/down-arrow buttons rather than dnd-kit — `ElementsEditor` just above (this
 * same file) already establishes that exact convention for a short ordered list
 * (`useReorderElements`/`handleMove`), attached-image counts here run single digits same as
 * screenplay elements, and arrow buttons are keyboard-operable with zero extra wiring, unlike
 * dnd-kit's drag path (which needs its own `KeyboardSensor`, see `beat-board.tsx`) — no reason
 * to reach for a heavier mechanism for a list this short. "Make cover" is the fast path for
 * the common case: move one image to the front without manually walking it up past every
 * other attached image; `nodes.tsx` reads `images?.[0]` as the node's cover thumbnail. */
function SceneImagesSection({ sceneId }: { sceneId: string }) {
  const { data: attached } = useEntityImages('scene', sceneId)
  const { data: pool } = useImages('finalized_scene')
  const attachImage = useAttachImage()
  const detachImage = useDetachImage()
  const uploadImage = useUploadImage()
  const reorderImages = useReorderEntityImages('scene', sceneId)
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Multi-select state for the "Attach existing" popover — the popover stays open across
  // individual picks (unlike the old single-pick-and-close `handlePickExisting`), and the
  // selection is only committed (and cleared) on explicit confirm or on close.
  const [attachMenuOpen, setAttachMenuOpen] = useState(false)
  const [selectedToAttach, setSelectedToAttach] = useState<Set<string>>(new Set())
  const [isAttaching, setIsAttaching] = useState(false)

  const attachedIds = new Set((attached ?? []).map((image) => image.id))
  const pickable = (pool ?? []).filter((image) => !attachedIds.has(image.id))

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    uploadImage.mutate(
      { file, bucket: 'finalized_scene' },
      {
        onSuccess: (image) =>
          attachImage.mutate({ imageId: image.id, entity_type: 'scene', entity_id: sceneId, role: 'finalized' }),
      },
    )
  }

  function toggleSelectedToAttach(imageId: string) {
    setSelectedToAttach((prev) => {
      const next = new Set(prev)
      if (next.has(imageId)) next.delete(imageId)
      else next.add(imageId)
      return next
    })
  }

  function handleAttachMenuOpenChange(open: boolean) {
    setAttachMenuOpen(open)
    if (!open) setSelectedToAttach(new Set())
  }

  /** Attaches every currently-checked pickable image in parallel via the existing single-image
   * `useAttachImage` mutation, then invalidates the attached-images query exactly once — not
   * once per image — after all of them have settled. If one attach call fails, `Promise.all`
   * rejects; `useAttachImage`'s own `onError` already toasts which image failed, so we just
   * make sure we still invalidate afterward (rather than leaving stale state for the ones that
   * DID succeed) and close the popover either way. */
  async function handleConfirmAttach() {
    const imageIds = Array.from(selectedToAttach)
    if (imageIds.length === 0) return
    setIsAttaching(true)
    try {
      await Promise.all(
        imageIds.map((imageId) =>
          attachImage.mutateAsync({ imageId, entity_type: 'scene', entity_id: sceneId, role: 'finalized' }),
        ),
      )
    } catch {
      // Individual failures are already surfaced via useAttachImage's onError toast.
    } finally {
      queryClient.invalidateQueries({ queryKey: ['entity-images', 'scene', sceneId] })
      queryClient.invalidateQueries({ queryKey: ['book-images'] })
      setSelectedToAttach(new Set())
      setIsAttaching(false)
      setAttachMenuOpen(false)
    }
  }

  function handleDetach(imageId: string) {
    detachImage.mutate({ imageId, entity_type: 'scene', entity_id: sceneId, role: 'finalized' })
  }

  function handleMove(index: number, direction: -1 | 1) {
    if (!attached) return
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= attached.length) return
    const reordered = [...attached]
    const [moved] = reordered.splice(index, 1)
    reordered.splice(targetIndex, 0, moved)
    reorderImages.mutate(reordered.map((image) => image.id))
  }

  /** Moves one image to the front of the order (→ becomes the cover) without disturbing the
   * relative order of the rest. */
  function handleMakeCover(imageId: string) {
    if (!attached) return
    const target = attached.find((image) => image.id === imageId)
    if (!target) return
    const reordered = [target, ...attached.filter((image) => image.id !== imageId)]
    reorderImages.mutate(reordered.map((image) => image.id))
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label>Images</Label>
        <div className="flex items-center gap-1">
          <DropdownMenu open={attachMenuOpen} onOpenChange={handleAttachMenuOpenChange}>
            {pickable.length === 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button variant="outline" size="sm" disabled className="gap-1 text-xs">
                      <ImagePlus className="size-3.5" />
                      Attach existing
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  No other finalized images available to attach yet — upload one first.
                </TooltipContent>
              </Tooltip>
            ) : (
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1 text-xs">
                  <ImagePlus className="size-3.5" />
                  Attach existing
                </Button>
              </DropdownMenuTrigger>
            )}
            <DropdownMenuContent align="end" className="max-h-64 w-56">
              {pickable.length === 0 ? (
                <p className="px-2 py-1.5 text-xs text-muted-foreground">
                  No other finalized images to attach.
                </p>
              ) : (
                <>
                  {pickable.map((image) => (
                    <DropdownMenuCheckboxItem
                      key={image.id}
                      checked={selectedToAttach.has(image.id)}
                      onCheckedChange={() => toggleSelectedToAttach(image.id)}
                      onSelect={(event) => event.preventDefault()}
                      className="gap-2"
                    >
                      <img
                        src={imageThumbUrl(image.id)}
                        alt=""
                        className="size-6 rounded object-cover"
                      />
                      <span className="truncate">{image.display_name}</span>
                    </DropdownMenuCheckboxItem>
                  ))}
                  <DropdownMenuSeparator />
                  <div className="px-1 pb-1">
                    <Button
                      type="button"
                      size="sm"
                      className="w-full text-xs"
                      disabled={selectedToAttach.size === 0 || isAttaching}
                      onClick={handleConfirmAttach}
                    >
                      {isAttaching
                        ? 'Attaching…'
                        : selectedToAttach.size === 0
                          ? 'Attach'
                          : `Attach ${selectedToAttach.size} image${selectedToAttach.size === 1 ? '' : 's'}`}
                    </Button>
                  </div>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadImage.isPending}
            className="gap-1 text-xs"
          >
            <Plus className="size-3.5" />
            {uploadImage.isPending ? 'Uploading…' : 'Upload'}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      </div>

      {/* Surfaces the `accept` list above up front — otherwise the only feedback for an
          unsupported file (e.g. HEIC, TIFF) is the native file picker silently graying it out,
          or a rejection after the fact. */}
      <p className="text-right text-[11px] text-muted-foreground">PNG, JPEG, WebP, or GIF</p>

      {(attached?.length ?? 0) === 0 ? (
        <p className="text-xs text-muted-foreground">No images attached to this scene yet.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {attached!.map((image, index) => (
            <div key={image.id} className="group flex flex-col items-center gap-1">
              <div className="relative size-14 overflow-hidden rounded-lg border border-border">
                <img
                  src={imageThumbUrl(image.id)}
                  alt={image.display_name}
                  className="size-full object-cover"
                />
                {index === 0 && (
                  <span className="absolute top-0.5 left-0.5 rounded bg-background/80 px-1 text-[9px] font-medium leading-4 text-foreground">
                    Cover
                  </span>
                )}
                <button
                  type="button"
                  aria-label={`Detach ${image.display_name}`}
                  onClick={() => handleDetach(image.id)}
                  disabled={detachImage.isPending}
                  className="absolute top-0.5 right-0.5 rounded-full bg-background/80 p-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <X className="size-3" />
                </button>
              </div>
              <div className="flex items-center justify-center gap-0.5">
                <button
                  type="button"
                  aria-label={`Move ${image.display_name} earlier`}
                  onClick={() => handleMove(index, -1)}
                  disabled={index === 0 || reorderImages.isPending}
                  className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
                >
                  <ArrowUp className="size-3" />
                </button>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label={`Make ${image.display_name} the cover image`}
                      onClick={() => handleMakeCover(image.id)}
                      disabled={index === 0 || reorderImages.isPending}
                      className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
                    >
                      <Star className="size-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent>Make cover image</TooltipContent>
                </Tooltip>
                <button
                  type="button"
                  aria-label={`Move ${image.display_name} later`}
                  onClick={() => handleMove(index, 1)}
                  disabled={index === attached!.length - 1 || reorderImages.isPending}
                  className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
                >
                  <ArrowDown className="size-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Script-book body: the structured screenplay elements list (docs/03
 * `screenplay_elements`, docs/06 Phase 2 task G5). Never touches the Scene's own
 * `description` field — elements are a fully separate, ordered child collection. */
function ElementsEditor({ sceneId }: { sceneId: string }) {
  const { data: elements, isLoading } = useElements(sceneId)
  const createElement = useCreateElement(sceneId)
  const updateElement = useUpdateElement(sceneId)
  const deleteElement = useDeleteElement(sceneId)
  const reorderElements = useReorderElements(sceneId)

  const [drafts, setDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!elements) return
    setDrafts(Object.fromEntries(elements.map((el) => [el.id, el.text])))
  }, [elements])

  const rows = elements ?? []

  function handleTextBlur(elementId: string) {
    const draft = drafts[elementId]
    const original = rows.find((row) => row.id === elementId)?.text
    if (draft === undefined || draft === original) return
    updateElement.mutate({ id: elementId, text: draft })
  }

  function handleMove(index: number, direction: -1 | 1) {
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= rows.length) return
    const reordered = [...rows]
    const [moved] = reordered.splice(index, 1)
    reordered.splice(targetIndex, 0, moved)
    reorderElements.mutate(reordered.map((row) => row.id))
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <Label>Screenplay elements</Label>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={createElement.isPending}>
              <Plus className="size-3.5" />
              Add element
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {ELEMENT_TYPES.map((elementType) => (
              <DropdownMenuItem
                key={elementType}
                onSelect={() => createElement.mutate({ element_type: elementType, text: '' })}
              >
                {ELEMENT_TYPE_LABELS[elementType]}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading elements…</p>
      ) : rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No elements yet — add a scene heading to get started.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((row, index) => (
            <ElementRow
              key={row.id}
              sceneId={sceneId}
              row={row}
              draftText={drafts[row.id] ?? row.text}
              onDraftChange={(value) => setDrafts((prev) => ({ ...prev, [row.id]: value }))}
              onDraftAccepted={(value) => setDrafts((prev) => ({ ...prev, [row.id]: value }))}
              onBlur={() => handleTextBlur(row.id)}
              onTypeChange={(value) => updateElement.mutate({ id: row.id, element_type: value })}
              onMoveUp={() => handleMove(index, -1)}
              onMoveDown={() => handleMove(index, 1)}
              onDelete={() => deleteElement.mutate(row.id)}
              moveUpDisabled={index === 0 || reorderElements.isPending}
              moveDownDisabled={index === rows.length - 1 || reorderElements.isPending}
              deletePending={deleteElement.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** One screenplay element row: type Select + real Enhance ✨ (docs/06 Phase 2 task H2) +
 * reorder/delete + the text Textarea. Enhance only streams a suggestion into local
 * state — Accept is the sole writer (via `useUpdateElement`); Reject leaves the row's
 * saved text and draft untouched. A separate component (rather than inline in the
 * `.map`) so each row gets its own `useEnhance()` instance/state. */
function ElementRow({
  sceneId,
  row,
  draftText,
  onDraftChange,
  onDraftAccepted,
  onBlur,
  onTypeChange,
  onMoveUp,
  onMoveDown,
  onDelete,
  moveUpDisabled,
  moveDownDisabled,
  deletePending,
}: {
  sceneId: string
  row: ScreenplayElement
  draftText: string
  onDraftChange: (value: string) => void
  onDraftAccepted: (value: string) => void
  onBlur: () => void
  onTypeChange: (value: ScreenplayElementType) => void
  onMoveUp: () => void
  onMoveDown: () => void
  onDelete: () => void
  moveUpDisabled: boolean
  moveDownDisabled: boolean
  deletePending: boolean
}) {
  const updateElement = useUpdateElement(sceneId)
  const enhance = useEnhance()
  const [reviewing, setReviewing] = useState(false)
  const textFieldRef = useRef<HTMLTextAreaElement | null>(null)

  function handleEnhanceClick() {
    setReviewing(true)
    enhance.start({
      mode: 'grammar',
      text: draftText,
      scene_id: sceneId,
      field: 'element',
      entity_type: 'screenplay_element',
      entity_id: row.id,
    })
  }

  // The ONLY writer: PATCHes this element's text, then updates the local draft so the
  // Textarea reflects it immediately. Never called from Reject.
  function handleAccept(finalText: string) {
    onDraftAccepted(finalText)
    updateElement.mutate({ id: row.id, text: finalText })
    if (enhance.logId) acceptLog(enhance.logId, true)
    setReviewing(false)
  }

  // Writes NOTHING — the row's draft/saved text is untouched.
  function handleReject() {
    if (enhance.logId) acceptLog(enhance.logId, false)
    setReviewing(false)
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-border p-2.5">
      <div className="flex items-center gap-1.5">
        <Select value={row.element_type} onValueChange={(value) => onTypeChange(value as ScreenplayElementType)}>
          <SelectTrigger size="sm" className="flex-1">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ELEMENT_TYPES.map((elementType) => (
              <SelectItem key={elementType} value={elementType}>
                {ELEMENT_TYPE_LABELS[elementType]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={handleEnhanceClick}
                disabled={enhance.isStreaming || draftText.trim().length === 0}
                aria-label="Enhance element"
              >
                <Sparkles className="size-3.5" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>Grammar & clarity pass — you review before anything is saved</TooltipContent>
        </Tooltip>

        <MicButton
          fieldRef={textFieldRef}
          label="element text"
          onTranscript={(text) => onDraftChange(insertAtCaret(textFieldRef.current, draftText, text))}
        />

        <Button variant="ghost" size="icon-sm" onClick={onMoveUp} disabled={moveUpDisabled} aria-label="Move up">
          <ArrowUp className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onMoveDown}
          disabled={moveDownDisabled}
          aria-label="Move down"
        >
          <ArrowDown className="size-3.5" />
        </Button>
        <Button variant="ghost" size="icon-sm" onClick={onDelete} disabled={deletePending} aria-label="Delete element">
          <Trash2 className="size-3.5" />
        </Button>
      </div>
      <Textarea
        ref={textFieldRef}
        value={draftText}
        onChange={(event) => onDraftChange(event.target.value)}
        onBlur={onBlur}
        placeholder={row.element_type === 'scene_heading' ? 'INT. LOCATION - DAY' : 'Element text…'}
        className="min-h-16 font-mono text-xs"
      />
      {reviewing && (
        <EnhanceDiff
          original={draftText}
          enhanced={enhance.streamedText}
          provider={enhance.provider}
          isStreaming={enhance.isStreaming}
          acceptPending={updateElement.isPending}
          onAccept={handleAccept}
          onReject={handleReject}
        />
      )}
      {enhance.error && <p className="text-xs text-destructive">Enhance failed: {enhance.error}</p>}
    </div>
  )
}

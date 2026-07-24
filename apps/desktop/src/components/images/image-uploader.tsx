import { useRef, useState, type DragEvent } from 'react'
import { Loader2, UploadCloud } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUploadImage } from '@/queries/images'
import type { ImageBucket, ImageRead } from '@/lib/api'

/**
 * Click-to-pick + drag-drop image upload control (docs/06 Phase 5 task FE-A). Errors
 * (413/415/422) surface as sonner toasts from `useUploadImage` itself — this component only
 * tracks drag-over styling and the busy state.
 */
export function ImageUploader({
  bucket,
  onUploaded,
  className,
}: {
  bucket: ImageBucket
  onUploaded?: (image: ImageRead) => void
  className?: string
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const uploadImage = useUploadImage()

  function handleFile(file: File | undefined) {
    if (!file) return
    uploadImage.mutate({ file, bucket }, { onSuccess: (image) => onUploaded?.(image) })
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    handleFile(e.dataTransfer.files?.[0])
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload an image — click to pick a file, or drag one here"
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click()
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={cn(
        'flex min-h-28 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed border-border text-center transition-colors',
        dragOver && 'border-primary bg-primary/5',
        uploadImage.isPending && 'pointer-events-none opacity-60',
        className,
      )}
    >
      {uploadImage.isPending ? (
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      ) : (
        <UploadCloud className="size-5 text-muted-foreground" />
      )}
      <p className="text-sm font-medium">
        {uploadImage.isPending ? 'Uploading…' : 'Drop an image, or click to pick one'}
      </p>
      <p className="text-xs text-muted-foreground">PNG, JPEG, WebP, or GIF — up to 10MB.</p>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        className="hidden"
        onChange={(e) => {
          handleFile(e.target.files?.[0])
          e.target.value = ''
        }}
      />
    </div>
  )
}

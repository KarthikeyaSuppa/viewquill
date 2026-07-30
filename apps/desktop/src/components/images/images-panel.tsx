import { useMemo, useState } from 'react'
import { BookOpen, Grip, Images as ImagesIcon, LayoutGrid, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ImageUploader } from '@/components/images/image-uploader'
import { ImageCard } from '@/components/images/image-card'
import { GalleryZoomView } from '@/components/images/gallery-zoom-view'
import { useBookImages, useImages } from '@/queries/images'
import type { ImageBucket } from '@/lib/api'

type GalleryView = 'pool' | 'book'
type BucketFilter = ImageBucket | 'all'
type LayoutMode = 'grid' | 'gallery'

const BUCKET_OPTIONS: { value: BucketFilter; label: string }[] = [
  { value: 'all', label: 'All buckets' },
  { value: 'reference_pool', label: 'Reference pool' },
  { value: 'finalized_scene', label: 'Finalized scene' },
]

/**
 * The Images tab (docs/06 Phase 5 task FE-A) — the reference-pool gallery plus a
 * Book-scoped export-preview toggle. "Reference pool" is the editable gallery (search, tag
 * filter, bucket filter, upload); "In this Book" is `useBookImages` — a read-only join
 * showing exactly what this Book's export will bundle (images attached to the Book itself,
 * to any Scene on its canvas, or to any Codex entry linked to those scenes; see
 * app/services/entity_images_service.gather_book_images on the sidecar).
 */
export function ImagesPanel({ bookId }: { bookId: string }) {
  const [view, setView] = useState<GalleryView>('pool')
  const [layout, setLayout] = useState<LayoutMode>('grid')
  const [search, setSearch] = useState('')
  const [bucket, setBucket] = useState<BucketFilter>('all')
  const [selectedTag, setSelectedTag] = useState<string | null>(null)

  const { data: poolImages, isLoading: poolLoading } = useImages(
    bucket === 'all' ? undefined : bucket,
    search.trim() || undefined,
  )
  const { data: bookImages, isLoading: bookLoading } = useBookImages(bookId)

  // Tag chips are derived from the currently-loaded (bucket+search-filtered) result set
  // rather than a dedicated "list all tags" endpoint (there isn't one) — clicking a chip
  // then filters that same set client-side by `tags.includes(selectedTag)`, so switching
  // tags never has to round-trip while chips stay visible for every tag in view.
  const availableTags = useMemo(() => {
    const set = new Set<string>()
    for (const image of poolImages ?? []) {
      for (const tag of image.tags) set.add(tag)
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [poolImages])

  const visiblePoolImages = useMemo(() => {
    if (!selectedTag) return poolImages ?? []
    return (poolImages ?? []).filter((image) => image.tags.includes(selectedTag))
  }, [poolImages, selectedTag])

  return (
    <div className="mt-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          className="glass glass-edge flex items-center gap-1 rounded-full p-1"
          role="tablist"
          aria-label="Reference pool or this Book's export preview"
        >
          <Button
            type="button"
            size="sm"
            variant={view === 'pool' ? 'secondary' : 'ghost'}
            className="rounded-full"
            role="tab"
            aria-selected={view === 'pool'}
            onClick={() => setView('pool')}
          >
            <ImagesIcon className="size-4" />
            Reference pool
          </Button>
          <Button
            type="button"
            size="sm"
            variant={view === 'book' ? 'secondary' : 'ghost'}
            className="rounded-full"
            role="tab"
            aria-selected={view === 'book'}
            onClick={() => setView('book')}
          >
            <BookOpen className="size-4" />
            In this Book
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {view === 'pool' && (
            <>
              <Input
                aria-label="Search images"
                placeholder="Search name, description, tags…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-56"
              />
              <Select value={bucket} onValueChange={(v) => setBucket(v as BucketFilter)}>
                <SelectTrigger size="sm" className="w-40" aria-label="Bucket filter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BUCKET_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}

          <div
            className="glass glass-edge flex items-center gap-1 rounded-full p-1"
            role="tablist"
            aria-label="Grid or draggable gallery layout"
          >
            <Button
              type="button"
              size="sm"
              variant={layout === 'grid' ? 'secondary' : 'ghost'}
              className="rounded-full"
              role="tab"
              aria-selected={layout === 'grid'}
              onClick={() => setLayout('grid')}
            >
              <LayoutGrid className="size-4" />
              Grid
            </Button>
            <Button
              type="button"
              size="sm"
              variant={layout === 'gallery' ? 'secondary' : 'ghost'}
              className="rounded-full"
              role="tab"
              aria-selected={layout === 'gallery'}
              onClick={() => setLayout('gallery')}
            >
              <Grip className="size-4" />
              Gallery
            </Button>
          </div>
        </div>
      </div>

      {view === 'pool' ? (
        <>
          {availableTags.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {availableTags.map((tag) => (
                <Badge
                  key={tag}
                  variant={selectedTag === tag ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setSelectedTag(selectedTag === tag ? null : tag)}
                >
                  {tag}
                </Badge>
              ))}
              {selectedTag && (
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  className="gap-1"
                  onClick={() => setSelectedTag(null)}
                >
                  <X className="size-3" />
                  Clear
                </Button>
              )}
            </div>
          )}

          <ImageUploader bucket={bucket === 'all' ? 'reference_pool' : bucket} />

          {poolLoading ? (
            <GallerySkeleton />
          ) : visiblePoolImages.length === 0 ? (
            <EmptyState
              message={
                search || selectedTag
                  ? 'No images match this search/filter.'
                  : 'No images yet — upload one above.'
              }
            />
          ) : layout === 'gallery' ? (
            <GalleryZoomView images={visiblePoolImages} bookId={bookId} />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {visiblePoolImages.map((image) => (
                <ImageCard key={image.id} image={image} bookId={bookId} />
              ))}
            </div>
          )}
        </>
      ) : (
        <>
          <p className="glass glass-edge rounded-xl px-4 py-3 text-sm text-muted-foreground">
            This shows exactly what this Book's export will bundle — every image attached to
            the Book, to a Scene on its Canvas, or to a Codex entry linked to one of those
            Scenes. Read-only: rename/tag/delete an image from the Reference pool view.
          </p>
          {bookLoading ? (
            <GallerySkeleton />
          ) : !bookImages || bookImages.length === 0 ? (
            <EmptyState message="Nothing would be bundled yet — attach images to this Book, its Scenes, or their Codex entries." />
          ) : layout === 'gallery' ? (
            <GalleryZoomView images={bookImages} bookId={bookId} readOnly />
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {bookImages.map((image) => (
                <ImageCard key={image.id} image={image} readOnly bookId={bookId} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="glass glass-edge flex min-h-[160px] items-center justify-center rounded-2xl px-8 py-10 text-center text-sm text-muted-foreground">
      {message}
    </div>
  )
}

function GallerySkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5" aria-hidden>
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="aspect-square rounded-2xl" />
      ))}
    </div>
  )
}

import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import { EllipsisVertical, Pencil, Plus, Shuffle, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
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
import {
  useBooks,
  useConvertBook,
  useCreateBook,
  useDeleteBook,
  useUpdateBook,
  type Book,
  type BookType,
} from '@/queries/books'
import { LottiePlayer } from '@/lib/lottie'

const BOOK_TYPES: { value: BookType; label: string }[] = [
  { value: 'story_book', label: 'Story Book' },
  { value: 'movie_script', label: 'Movie Script' },
  { value: 'short_film_script', label: 'Short Film Script' },
  { value: 'single_scene', label: 'Single Scene' },
]

const BOOK_TYPE_LABELS: Record<BookType, string> = {
  story_book: 'Story Book',
  movie_script: 'Movie Script',
  short_film_script: 'Short Film Script',
  single_scene: 'Single Scene',
}

function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const diffMin = Math.round(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHour = Math.round(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h ago`
  const diffDay = Math.round(diffHour / 24)
  if (diffDay < 7) return `${diffDay}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

const listVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
}

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0 },
}

/** The Library (Phase 1 home): every book, with create/rename/convert/delete. */
export function LibraryScreen() {
  const { data: books, isLoading } = useBooks()
  const [newOpen, setNewOpen] = useState(false)

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
          <p className="text-sm text-muted-foreground">Every story, script, and scene lives here.</p>
        </div>
        <Button onClick={() => setNewOpen(true)}>
          <Plus className="size-4" />
          New Book
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-2xl" />
          ))}
        </div>
      ) : !books || books.length === 0 ? (
        <EmptyState onCreate={() => setNewOpen(true)} />
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          initial="hidden"
          animate="show"
          variants={listVariants}
        >
          {books.map((book) => (
            <BookCard key={book.id} book={book} />
          ))}
        </motion.div>
      )}

      <NewBookDialog open={newOpen} onOpenChange={setNewOpen} />
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="glass glass-edge flex flex-col items-center gap-3 rounded-2xl px-8 py-16 text-center">
      <LottiePlayer
        animationData={() => import('../assets/lottie/empty-state.json')}
        loop
        ariaHidden
        className="size-32"
      />
      <p className="text-base font-medium">No books yet — start your first story.</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        Story books, scripts, and scenes all begin the same way: with a title.
      </p>
      <Button onClick={onCreate} className="mt-2">
        <Plus className="size-4" />
        New Book
      </Button>
    </div>
  )
}

function BookCard({ book }: { book: Book }) {
  const navigate = useNavigate()
  const [renameOpen, setRenameOpen] = useState(false)
  const [convertOpen, setConvertOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  return (
    <>
      <motion.div variants={itemVariants}>
        <Card
          role="button"
          tabIndex={0}
          onClick={() => navigate(`/book/${book.id}`)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') navigate(`/book/${book.id}`)
          }}
          className="glass glass-edge cursor-pointer gap-3 rounded-2xl border-0 py-5 shadow-none transition-transform hover:-translate-y-0.5"
        >
          <CardHeader className="grid-cols-[1fr_auto] items-start px-5">
            <div className="flex flex-col gap-1.5">
              <CardTitle className="text-base">{book.title}</CardTitle>
              <Badge variant="secondary" className="w-fit">
                {BOOK_TYPE_LABELS[book.book_type]}
              </Badge>
            </div>
            {/* Stops clicks from bubbling to the card's navigate handler (React's synthetic
                events bubble through the component tree, not the DOM, so this must wrap the
                whole portal-rendered menu, not just the trigger). */}
            <div onClick={(e) => e.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" aria-label="Book actions">
                    <EllipsisVertical className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" onCloseAutoFocus={(e) => e.preventDefault()}>
                  <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                    <Pencil />
                    Rename
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => setConvertOpen(true)}>
                    <Shuffle />
                    Convert type
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => setDeleteOpen(true)}>
                    <Trash2 />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </CardHeader>
          <CardContent className="px-5 text-xs text-muted-foreground">
            Updated {formatRelative(book.updated_at)}
          </CardContent>
        </Card>
      </motion.div>

      <RenameDialog book={book} open={renameOpen} onOpenChange={setRenameOpen} />
      <ConvertDialog book={book} open={convertOpen} onOpenChange={setConvertOpen} />
      <DeleteAlert book={book} open={deleteOpen} onOpenChange={setDeleteOpen} />
    </>
  )
}

function NewBookDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const createBook = useCreateBook()
  const [title, setTitle] = useState('')
  const [bookType, setBookType] = useState<BookType>('story_book')

  useEffect(() => {
    if (open) {
      setTitle('')
      setBookType('story_book')
    }
  }, [open])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) return
    createBook.mutate(
      { title: trimmed, book_type: bookType },
      {
        onSuccess: (book) => {
          onOpenChange(false)
          navigate(`/book/${book.id}`)
        },
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New book</DialogTitle>
          <DialogDescription>Start a story book, script, or scene.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="new-book-title">Title</Label>
            <Input
              id="new-book-title"
              autoFocus
              placeholder="Untitled"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="new-book-type">Book type</Label>
            <Select value={bookType} onValueChange={(v) => setBookType(v as BookType)}>
              <SelectTrigger id="new-book-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BOOK_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createBook.isPending || !title.trim()}>
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function RenameDialog({
  book,
  open,
  onOpenChange,
}: {
  book: Book
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const updateBook = useUpdateBook()
  const [title, setTitle] = useState(book.title)

  useEffect(() => {
    if (open) setTitle(book.title)
  }, [open, book.title])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = title.trim()
    if (!trimmed) return
    updateBook.mutate(
      { id: book.id, title: trimmed },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename book</DialogTitle>
          <DialogDescription>Give “{book.title}” a new title.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="rename-title">Title</Label>
            <Input
              id="rename-title"
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={updateBook.isPending || !title.trim()}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ConvertDialog({
  book,
  open,
  onOpenChange,
}: {
  book: Book
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const convertBook = useConvertBook()
  const [bookType, setBookType] = useState<BookType>(book.book_type)

  useEffect(() => {
    if (open) setBookType(book.book_type)
  }, [open, book.book_type])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    convertBook.mutate(
      { id: book.id, book_type: bookType },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Convert book type</DialogTitle>
          <DialogDescription>Change how “{book.title}” is structured.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="convert-type">Book type</Label>
            <Select value={bookType} onValueChange={(v) => setBookType(v as BookType)}>
              <SelectTrigger id="convert-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BOOK_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={convertBook.isPending || bookType === book.book_type}
            >
              Convert
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteAlert({
  book,
  open,
  onOpenChange,
}: {
  book: Book
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const deleteBook = useDeleteBook()

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete “{book.title}”?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the book and everything inside it. This can’t be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={deleteBook.isPending}
            onClick={(e) => {
              e.preventDefault()
              deleteBook.mutate(book.id, { onSuccess: () => onOpenChange(false) })
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

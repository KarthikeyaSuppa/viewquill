import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useBook, type BookType } from '@/queries/books'

const BOOK_TYPE_LABELS: Record<BookType, string> = {
  story_book: 'Story Book',
  movie_script: 'Movie Script',
  short_film_script: 'Short Film Script',
  single_scene: 'Single Scene',
}

/** The Book shell (Phase 1): header + Canvas/Outline/Draft tabs. Panels are wired later. */
export function BookScreen() {
  const { bookId } = useParams<{ bookId: string }>()
  const navigate = useNavigate()
  const { data: book, isLoading } = useBook(bookId)

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => navigate('/')}
          aria-label="Back to Library"
        >
          <ArrowLeft className="size-4" />
        </Button>

        {isLoading || !book ? (
          <Skeleton className="h-7 w-48" />
        ) : (
          <>
            <h1 className="text-2xl font-semibold tracking-tight">{book.title}</h1>
            <Badge variant="secondary">{BOOK_TYPE_LABELS[book.book_type]}</Badge>
          </>
        )}
      </div>

      <Tabs defaultValue="canvas">
        <TabsList>
          <TabsTrigger value="canvas">Canvas</TabsTrigger>
          <TabsTrigger value="outline">Outline</TabsTrigger>
          <TabsTrigger value="draft">Draft</TabsTrigger>
        </TabsList>
        <TabsContent value="canvas">
          <EmptyPanel note="Coming in Phase 2." />
        </TabsContent>
        <TabsContent value="outline">
          <EmptyPanel note="Coming in Phase 4." />
        </TabsContent>
        <TabsContent value="draft">
          <EmptyPanel note="Coming in Phase 6." />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function EmptyPanel({ note }: { note: string }) {
  return (
    <div className="glass glass-edge mt-4 flex min-h-[240px] items-center justify-center rounded-2xl text-sm text-muted-foreground">
      {note}
    </div>
  )
}

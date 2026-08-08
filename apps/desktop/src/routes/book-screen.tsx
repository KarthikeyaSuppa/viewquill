import { useCallback, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Plus, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useBook, type BookType } from '@/queries/books'
import { CanvasPanel, NODE_MENU } from '@/components/canvas/canvas-panel'
import { OutlinePanel } from '@/components/outline/outline-panel'
import { ImagesPanel } from '@/components/images/images-panel'
import { DraftPanel } from '@/components/draft/draft-panel'
import { CharactersPanel } from '@/components/codex/characters-panel'
import { useCanvasActionsStore } from '@/stores/canvas-actions'
import { playPageTurn, useDelight } from '@/lib/delight'
import { useIndicatorRefs, WobblyIndicator } from '@/components/wobbly-indicator'

const BOOK_TYPE_LABELS: Record<BookType, string> = {
  story_book: 'Story Book',
  movie_script: 'Movie Script',
  short_film_script: 'Short Film Script',
  single_scene: 'Single Scene',
}

type BookTab = 'canvas' | 'characters' | 'outline' | 'images' | 'draft'

/** True when the browser supports the View Transitions API — feature-detected so this is
 * a no-op fallback (a plain state update) everywhere it isn't (docs/10 §5). */
function supportsViewTransitions(): boolean {
  return typeof document !== 'undefined' && typeof document.startViewTransition === 'function'
}

/** The Book shell (Phase 1): header + Canvas/Outline/Draft tabs. Panels are wired later.
 * Tab switches (docs/10 §5 "delight base") cross-fade via the View Transitions API when
 * supported, and only when `useDelight().motionOk` — i.e. never at delight_level 'calm'
 * and never under `prefers-reduced-motion`, where switching is an instant, plain state
 * update. */
export function BookScreen() {
  const { bookId } = useParams<{ bookId: string }>()
  const navigate = useNavigate()
  const { data: book, isLoading } = useBook(bookId)
  const { motionOk, soundsOk } = useDelight()
  const [tab, setTab] = useState<BookTab>('canvas')
  const addNode = useCanvasActionsStore((s) => s.addNode)
  const addNodePending = useCanvasActionsStore((s) => s.addNodePending)

  // Wobbly underline (PHASE-UI-EFFECTS.md #9) — replaces the default shadcn Tabs pill
  // active-treatment (see `.wobbly-tabs` in index.css) with a single sliding underline, so
  // there's exactly one active-indicator on this tab bar rather than a pill *and* a bar
  // competing for attention.
  const tabsListRef = useRef<HTMLDivElement | null>(null)
  const { refs: tabItemRefs, setRef: setTabItemRef } = useIndicatorRefs<BookTab>()

  const handleTabChange = useCallback(
    (next: string) => {
      const nextTab = next as BookTab
      if (soundsOk) playPageTurn()

      if (motionOk && supportsViewTransitions()) {
        document.startViewTransition(() => setTab(nextTab))
      } else {
        setTab(nextTab)
      }
    },
    [motionOk, soundsOk],
  )

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

      <Tabs value={tab} onValueChange={handleTabChange}>
        <div className="flex items-center justify-between gap-3">
          <TabsList ref={tabsListRef} className="wobbly-tabs relative gap-1 bg-transparent p-0">
            <TabsTrigger value="canvas" ref={setTabItemRef('canvas')}>
              Canvas
            </TabsTrigger>
            <TabsTrigger value="characters" ref={setTabItemRef('characters')}>
              <Users className="size-3.5" />
              Characters
            </TabsTrigger>
            <TabsTrigger value="outline" ref={setTabItemRef('outline')}>
              Outline
            </TabsTrigger>
            <TabsTrigger value="images" ref={setTabItemRef('images')}>
              Images
            </TabsTrigger>
            <TabsTrigger value="draft" ref={setTabItemRef('draft')}>
              Draft
            </TabsTrigger>
            <WobblyIndicator
              containerRef={tabsListRef}
              activeElement={tabItemRefs.current.get(tab) ?? null}
              activeKey={tab}
              orientation="horizontal"
              className="rounded-full bg-primary"
            />
          </TabsList>

          {tab === 'canvas' && (
            <div className="flex items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" disabled={!addNode || addNodePending}>
                    <Plus className="size-4" />
                    Add node
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {NODE_MENU.map(({ nodeType, label, icon: Icon }) => (
                    <DropdownMenuItem key={nodeType} onSelect={() => addNode?.(nodeType)}>
                      <Icon />
                      {label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}
        </div>
        <TabsContent value="canvas">
          {bookId ? <CanvasPanel bookId={bookId} /> : <EmptyPanel note="Coming in Phase 2." />}
        </TabsContent>
        <TabsContent value="characters">
          {bookId ? <CharactersPanel bookId={bookId} /> : <EmptyPanel note="Open a Book to see its characters." />}
        </TabsContent>
        <TabsContent value="outline">
          {bookId ? (
            <OutlinePanel bookId={bookId} book={book} />
          ) : (
            <EmptyPanel note="Coming in Phase 4." />
          )}
        </TabsContent>
        <TabsContent value="images">
          {bookId ? <ImagesPanel bookId={bookId} /> : <EmptyPanel note="Coming in Phase 5." />}
        </TabsContent>
        <TabsContent value="draft">
          {bookId && book ? (
            <DraftPanel bookId={bookId} book={book} />
          ) : (
            <EmptyPanel note="Coming in Phase 6." />
          )}
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

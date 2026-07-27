import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useUpdateBook, type Book } from '@/queries/books'

interface FrontMatterEditorProps {
  bookId: string
  book: Book
}

/** Reads one of the four well-known `front_matter` keys as a string, coercing non-strings. */
function fieldValue(frontMatter: Record<string, unknown> | null | undefined, key: string): string {
  const value = frontMatter?.[key]
  if (value == null) return ''
  return typeof value === 'string' ? value : String(value)
}

/**
 * The Front Matter editor (docs/06 Phase 6 task FE-2) — a small, fixed set of well-known
 * `front_matter` fields (subtitle/author/dedication/preface), even though the field itself
 * is free-form JSON per the data model. `export_docx.py`/`export_pdf.py` iterate over
 * whatever keys are present, so this UI only ever writes the four keys it exposes and never
 * touches any others a future editor might add.
 *
 * Local draft state resyncs only on `book.id` change (mirrors `node-editor.tsx`'s
 * `[node?.data.sceneId]` and `codex-entry-dialog.tsx`'s `[entry.id]` — both deliberately
 * exclude the *content* fields from the effect's deps) so an in-progress edit is never
 * clobbered by a background refetch of the same book while this panel stays mounted.
 * Saving is an explicit Save button gated on a dirty check, matching the rename/description
 * fields in `image-detail.tsx` and `image-card.tsx`'s `RenameDialog` (not autosave-on-blur).
 */
export function FrontMatterEditor({ bookId, book }: FrontMatterEditorProps) {
  const updateBook = useUpdateBook()

  const [subtitle, setSubtitle] = useState(() => fieldValue(book.front_matter, 'subtitle'))
  const [author, setAuthor] = useState(() => fieldValue(book.front_matter, 'author'))
  const [dedication, setDedication] = useState(() => fieldValue(book.front_matter, 'dedication'))
  const [preface, setPreface] = useState(() => fieldValue(book.front_matter, 'preface'))

  // Reset local drafts only when a *different* book is loaded — never clobber an
  // in-progress edit just because this book's query refetched in the background.
  useEffect(() => {
    setSubtitle(fieldValue(book.front_matter, 'subtitle'))
    setAuthor(fieldValue(book.front_matter, 'author'))
    setDedication(fieldValue(book.front_matter, 'dedication'))
    setPreface(fieldValue(book.front_matter, 'preface'))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [book.id])

  const dirty =
    subtitle !== fieldValue(book.front_matter, 'subtitle') ||
    author !== fieldValue(book.front_matter, 'author') ||
    dedication !== fieldValue(book.front_matter, 'dedication') ||
    preface !== fieldValue(book.front_matter, 'preface')

  function handleSave() {
    const next: Record<string, string> = {}
    if (subtitle.trim()) next.subtitle = subtitle.trim()
    if (author.trim()) next.author = author.trim()
    if (dedication.trim()) next.dedication = dedication.trim()
    if (preface.trim()) next.preface = preface.trim()

    updateBook.mutate({
      id: bookId,
      front_matter: Object.keys(next).length > 0 ? next : null,
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Front matter</CardTitle>
        <CardDescription>
          Shown on the title page and ahead of the manuscript when you export — leave a field
          blank to leave it out entirely.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="front-matter-subtitle">Subtitle</Label>
          <Input
            id="front-matter-subtitle"
            value={subtitle}
            onChange={(event) => setSubtitle(event.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="front-matter-author">Author</Label>
          <Input
            id="front-matter-author"
            value={author}
            onChange={(event) => setAuthor(event.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="front-matter-dedication">Dedication</Label>
          <Textarea
            id="front-matter-dedication"
            className="manuscript min-h-20"
            value={dedication}
            onChange={(event) => setDedication(event.target.value)}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="front-matter-preface">Preface</Label>
          <Textarea
            id="front-matter-preface"
            className="manuscript min-h-32"
            value={preface}
            onChange={(event) => setPreface(event.target.value)}
          />
        </div>

        <Button
          size="sm"
          onClick={handleSave}
          disabled={!dirty || updateBook.isPending}
          className="self-start"
        >
          Save
        </Button>
      </CardContent>
    </Card>
  )
}

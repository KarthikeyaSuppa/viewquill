import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { useCompileExport, type ExportFormat } from '@/queries/export'
import type { Book } from '@/queries/books'
import { FrontMatterEditor } from '@/components/draft/front-matter-editor'
import { VersionList } from '@/components/draft/version-list'

interface DraftPanelProps {
  bookId: string
  book: Book
}

const ALWAYS_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: 'markdown', label: 'Markdown' },
  { format: 'docx', label: 'DOCX' },
  { format: 'pdf', label: 'PDF' },
]

const SCRIPT_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: 'fountain', label: 'Fountain' },
  { format: 'fdx', label: 'FDX' },
]

/**
 * The Draft tab (docs/06 Phase 6 task FE-3): front matter + "Compile & Export" + version
 * history. Fountain/FDX buttons only show for script-type Books, mirroring the
 * `isScriptBook` boolean in `src/components/canvas/canvas-panel.tsx`. `useCompileExport`
 * already toasts success/failure itself (src/queries/export.ts) — this component doesn't
 * add a second toast, same lesson noted in FE-2's front-matter editor around `useUpdateBook`.
 */
export function DraftPanel({ bookId, book }: DraftPanelProps) {
  const compileExport = useCompileExport(bookId)
  // Tracks which single format is currently compiling, so only that format's button shows a
  // spinner/disabled state — `compileExport.isPending` alone can't tell buttons apart.
  const [pendingFormat, setPendingFormat] = useState<ExportFormat | null>(null)

  const isScriptBook = book.book_type === 'movie_script' || book.book_type === 'short_film_script'
  const formats = isScriptBook ? [...ALWAYS_FORMATS, ...SCRIPT_FORMATS] : ALWAYS_FORMATS

  function handleCompile(format: ExportFormat) {
    setPendingFormat(format)
    compileExport.mutate(format, {
      onSettled: () => setPendingFormat(null),
    })
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      <FrontMatterEditor bookId={bookId} book={book} />

      <Card>
        <CardHeader>
          <CardTitle>Compile &amp; export</CardTitle>
          <CardDescription>
            Compiles the current Canvas into a downloadable file, adding it to the version
            history below.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">
            {formats.map(({ format, label }) => {
              const isThisPending = pendingFormat === format && compileExport.isPending
              return (
                <Button
                  key={format}
                  size="sm"
                  variant="outline"
                  disabled={compileExport.isPending}
                  onClick={() => handleCompile(format)}
                >
                  {isThisPending && <Loader2 className="size-3.5 animate-spin" />}
                  {label}
                </Button>
              )
            })}
          </div>

          <VersionList bookId={bookId} />
        </CardContent>
      </Card>
    </div>
  )
}

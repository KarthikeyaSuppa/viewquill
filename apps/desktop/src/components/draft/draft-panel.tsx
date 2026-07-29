import { useState } from 'react'
import { ChevronDown, ChevronUp, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { useCompileExport, type ExportFormat } from '@/queries/export'
import type { Book } from '@/queries/books'
import { useDelight } from '@/lib/delight'
import { FrontMatterEditor } from '@/components/draft/front-matter-editor'
import { ManuscriptReader } from '@/components/draft/manuscript-reader'
import { VersionList } from '@/components/draft/version-list'
import { ExportBundleDialog } from '@/components/bundle/export-dialog'
import { ImportBundleDialog } from '@/components/bundle/import-review-dialog'

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
  const { fireConfetti, fireDelightAccent } = useDelight()
  // Tracks which single format is currently compiling, so only that format's button shows a
  // spinner/disabled state — `compileExport.isPending` alone can't tell buttons apart.
  const [pendingFormat, setPendingFormat] = useState<ExportFormat | null>(null)

  const [exportBundleOpen, setExportBundleOpen] = useState(false)
  const [importBundleOpen, setImportBundleOpen] = useState(false)
  const [readerOpen, setReaderOpen] = useState(true)

  const isScriptBook = book.book_type === 'movie_script' || book.book_type === 'short_film_script'
  const formats = isScriptBook ? [...ALWAYS_FORMATS, ...SCRIPT_FORMATS] : ALWAYS_FORMATS

  function handleCompile(format: ExportFormat) {
    setPendingFormat(format)
    compileExport.mutate(format, {
      onSettled: () => setPendingFormat(null),
      // A successful compile — same delight tier as Enhance-accept: confetti fires at
      // both 'standard' and 'playful' only if flagged `major` (it isn't here, so this is
      // 'playful'-only in practice), the Lottie accent is 'playful'-only outright.
      onSuccess: () => {
        fireConfetti()
        fireDelightAccent()
      },
    })
  }

  return (
    <div className="mt-4 flex flex-col gap-4">
      <FrontMatterEditor bookId={bookId} book={book} />

      <Card>
        <CardHeader className="flex-row items-start justify-between">
          <div>
            <CardTitle>Manuscript reader</CardTitle>
            <CardDescription>
              A live, read-only preview of the fully compiled manuscript, in your reading
              settings' typography.
            </CardDescription>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setReaderOpen((open) => !open)}
            aria-expanded={readerOpen}
          >
            {readerOpen ? (
              <>
                <ChevronUp className="size-3.5" />
                Hide
              </>
            ) : (
              <>
                <ChevronDown className="size-3.5" />
                Show
              </>
            )}
          </Button>
        </CardHeader>
        {readerOpen && (
          <CardContent>
            <ManuscriptReader bookId={bookId} />
          </CardContent>
        )}
      </Card>

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

      <Card>
        <CardHeader>
          <CardTitle>Backup &amp; restore</CardTitle>
          <CardDescription>
            A full, encrypted snapshot of this Book — everything, not just the manuscript
            text — that you can restore later or move to another computer.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setExportBundleOpen(true)}>
            Export backup
          </Button>
          <Button size="sm" variant="outline" onClick={() => setImportBundleOpen(true)}>
            Import backup
          </Button>
        </CardContent>
      </Card>

      <ExportBundleDialog bookId={bookId} open={exportBundleOpen} onOpenChange={setExportBundleOpen} />
      <ImportBundleDialog open={importBundleOpen} onOpenChange={setImportBundleOpen} />
    </div>
  )
}

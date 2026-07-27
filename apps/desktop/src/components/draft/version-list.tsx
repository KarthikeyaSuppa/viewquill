import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useDraftVersions, draftDownloadUrl, type ExportFormat } from '@/queries/export'

interface VersionListProps {
  bookId: string
}

const FORMAT_LABELS: Record<ExportFormat, string> = {
  markdown: 'Markdown',
  docx: 'DOCX',
  pdf: 'PDF',
  fountain: 'Fountain',
  fdx: 'FDX',
}

/** Same relative-time formatting as `formatRelative` in `src/routes/library-screen.tsx` —
 * hand-duplicated rather than extracted to a shared util, matching this codebase's existing
 * convention of small per-file helpers over shared lib functions for one-off formatting. */
function formatGeneratedAt(iso: string): string {
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

/**
 * The draft-version history list (docs/06 Phase 6 task FE-3), backing the Draft tab's
 * "Compile & Export" section. Read-only — every row is a past `/export/{format}` compile,
 * newest first (server-sorted per `useDraftVersions`), with a `download` anchor styled as a
 * `Button` via `asChild` since no other download-link precedent exists yet in this codebase.
 */
export function VersionList({ bookId }: VersionListProps) {
  const { data: versions, isLoading } = useDraftVersions(bookId)

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>
  }

  if (!versions || versions.length === 0) {
    return (
      <div className="glass glass-edge flex min-h-[120px] items-center justify-center rounded-2xl px-8 py-10 text-center text-sm text-muted-foreground">
        No exports yet.
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {versions.map((version) => (
        <div
          key={version.id}
          className="glass glass-edge flex items-center justify-between gap-3 rounded-xl px-4 py-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{FORMAT_LABELS[version.format]}</Badge>
            <span className="text-sm text-muted-foreground">v{version.version_number}</span>
            {version.is_current && <Badge>Current</Badge>}
            <span className="text-sm text-muted-foreground">
              {formatGeneratedAt(version.generated_at)}
            </span>
          </div>

          <Button asChild size="sm" variant="outline">
            <a href={draftDownloadUrl(version.id)} download>
              Download
            </a>
          </Button>
        </div>
      ))}
    </div>
  )
}

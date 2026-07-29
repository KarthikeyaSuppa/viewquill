import { type FormEvent, useEffect, useState } from 'react'
import { TriangleAlert } from 'lucide-react'
import { ApiError } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  useApplyBundle,
  useInspectBundle,
  type ConflictResolution,
  type MergeReport,
} from '@/queries/bundle'

type Step = 'select' | 'review'

const RESOLUTION_OPTIONS: { value: ConflictResolution; label: string }[] = [
  { value: 'keep_local', label: 'Keep local' },
  { value: 'take_imported', label: 'Replace with imported' },
  { value: 'merge', label: 'Merge' },
]

/**
 * "Import backup" dialog (docs/06 Phase 7, final task) — two steps: inspect a `.quillproj`
 * file without writing anything, review what it would change, then apply with explicit
 * per-conflict resolutions. Never silently overwrites: every conflicting entity defaults to
 * "Keep local" and the user must actively choose otherwise (docs/01-PRODUCT-VISION.md).
 */
export function ImportBundleDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const inspectBundle = useInspectBundle()
  const applyBundle = useApplyBundle()

  const [step, setStep] = useState<Step>('select')
  const [file, setFile] = useState<File | null>(null)
  const [passphrase, setPassphrase] = useState('')
  const [report, setReport] = useState<MergeReport | null>(null)
  const [resolutions, setResolutions] = useState<Record<string, ConflictResolution>>({})

  // Reset the whole flow every time the dialog re-opens, same reasoning as the export
  // dialog resetting its passphrase field.
  useEffect(() => {
    if (open) {
      setStep('select')
      setFile(null)
      setPassphrase('')
      setReport(null)
      setResolutions({})
      inspectBundle.reset()
      applyBundle.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  function handleInspect(event: FormEvent) {
    event.preventDefault()
    if (!file || passphrase.length < 8) return
    inspectBundle.mutate(
      { file, passphrase },
      {
        onSuccess: (mergeReport) => {
          setReport(mergeReport)
          setStep('review')
        },
      },
    )
  }

  function handleApply() {
    if (!file || !report) return
    applyBundle.mutate(
      { file, passphrase, resolutions },
      {
        onSuccess: () => onOpenChange(false),
      },
    )
  }

  const inspectDetail =
    inspectBundle.error instanceof ApiError
      ? inspectBundle.error.detail ?? 'Could not read this backup file.'
      : inspectBundle.error
        ? 'Could not read this backup file.'
        : null
  const applyDetail =
    applyBundle.error instanceof ApiError
      ? applyBundle.error.detail ?? 'Could not apply this import.'
      : applyBundle.error
        ? 'Could not apply this import.'
        : null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Import backup</DialogTitle>
          <DialogDescription>
            Restores a <code className="rounded bg-muted px-1 py-0.5 text-xs">.quillproj</code>{' '}
            backup into your library. Nothing is written until you review and apply.
          </DialogDescription>
        </DialogHeader>

        {step === 'select' && (
          <form onSubmit={handleInspect} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bundle-import-file">Backup file</Label>
              <Input
                id="bundle-import-file"
                type="file"
                accept=".quillproj"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="bundle-import-passphrase">Passphrase</Label>
              <Input
                id="bundle-import-passphrase"
                type="password"
                autoComplete="current-password"
                value={passphrase}
                onChange={(event) => setPassphrase(event.target.value)}
              />
            </div>

            {inspectDetail && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                <p>{inspectDetail}</p>
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!file || passphrase.length < 8 || inspectBundle.isPending}>
                {inspectBundle.isPending ? 'Inspecting…' : 'Inspect'}
              </Button>
            </DialogFooter>
          </form>
        )}

        {step === 'review' && report && (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">
              {report.created.length} new, {report.matched.length} unchanged,{' '}
              {report.conflicts.length} conflict{report.conflicts.length === 1 ? '' : 's'}.
            </p>

            {report.asset_warnings.length > 0 && (
              <div className="flex flex-col gap-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                {report.asset_warnings.map((warning, index) => (
                  <div key={index} className="flex items-start gap-2">
                    <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                    <p>{warning}</p>
                  </div>
                ))}
              </div>
            )}

            {report.conflicts.length > 0 && (
              <ScrollArea className="max-h-72 rounded-md border p-3">
                <div className="flex flex-col gap-4">
                  {report.conflicts.map((conflict, index) => (
                    <div key={conflict.id}>
                      {index > 0 && <Separator className="mb-4" />}
                      <div className="mb-2 flex items-center gap-2">
                        <Badge variant="outline">{conflict.table}</Badge>
                        <span className="text-sm font-medium">{conflict.name}</span>
                      </div>
                      <p className="mb-2 text-xs text-muted-foreground">
                        Differs in: {conflict.differing_fields.join(', ')}
                      </p>
                      <RadioGroup
                        value={resolutions[conflict.id] ?? 'keep_local'}
                        onValueChange={(value) =>
                          setResolutions((prev) => ({
                            ...prev,
                            [conflict.id]: value as ConflictResolution,
                          }))
                        }
                        className="grid grid-cols-1 gap-2 sm:grid-cols-3"
                      >
                        {RESOLUTION_OPTIONS.map((option) => (
                          <div key={option.value} className="flex items-center gap-2">
                            <RadioGroupItem
                              id={`conflict-${conflict.id}-${option.value}`}
                              value={option.value}
                            />
                            <Label
                              htmlFor={`conflict-${conflict.id}-${option.value}`}
                              className="text-sm font-normal"
                            >
                              {option.label}
                            </Label>
                          </div>
                        ))}
                      </RadioGroup>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}

            {applyDetail && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                <p>{applyDetail}</p>
              </div>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setStep('select')}>
                Back
              </Button>
              <Button type="button" onClick={handleApply} disabled={applyBundle.isPending}>
                {applyBundle.isPending ? 'Applying…' : 'Apply import'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

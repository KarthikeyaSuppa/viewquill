import { useEffect, useState } from 'react'
import { ImagePlus, Plus, Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useCodexArcStates,
  useCodexEntries,
  useCodexRelationships,
  useCreateArcState,
  useCreateRelationship,
  useDeleteArcState,
  useDeleteRelationship,
  useUpdateCodex,
  useUploadImage,
  imageUrl,
} from '@/queries/codex'
import { useBooks } from '@/queries/books'
import type { CodexEntry } from '@/lib/api'
import {
  CHARACTER_ROLES,
  CHARACTER_TRAITS,
  FACTION_KINDS,
  LOCATION_KINDS,
  OBJECT_KINDS,
  RELATIONSHIP_TYPES,
  labelFor,
} from '@/lib/vocab'

/** Keys inside `custom_fields` that are managed by dedicated controls elsewhere in this
 * dialog (Details tab's guided Select/traits, or the backend's arc-state bookkeeping) —
 * excluded from the free-form Custom Fields editor so users can't fight the guided UI. */
const MANAGED_KEYS = new Set(['role', 'kind', 'traits'])
function isManagedKey(key: string): boolean {
  return MANAGED_KEYS.has(key) || key.startsWith('arc_')
}

/** The kind-vocab Select for this entry's `entry_type` — none for object types without one
 * (there are none currently, but keep this shape future-proof). */
function kindVocabFor(entryType: CodexEntry['entry_type']) {
  switch (entryType) {
    case 'character':
      return { key: 'role' as const, label: 'Role', options: CHARACTER_ROLES }
    case 'location':
      return { key: 'kind' as const, label: 'Kind', options: LOCATION_KINDS }
    case 'faction':
      return { key: 'kind' as const, label: 'Kind', options: FACTION_KINDS }
    case 'object_lore':
      return { key: 'kind' as const, label: 'Kind', options: OBJECT_KINDS }
    default:
      return null
  }
}

interface CustomFieldRow {
  key: string
  value: string
}

/**
 * The full Codex entity editor (docs/06-ROADMAP.md Phase 3 task FE-7). Opened from
 * `CodexPanel` (FE-8 wires the trigger) with one existing entry. Five tabs: Details,
 * Custom Fields, Relationships, Image, Arc States.
 *
 * All edits are explicit Save actions (no autosave/debounce) — matches the panel's
 * existing edit-mode pattern and never silently overwrites `custom_fields` keys owned by
 * another tab (docs/01-PRODUCT-VISION.md "never lose data, never silently overwrite").
 */
export function CodexEntryDialog({
  entry,
  open,
  onOpenChange,
  books,
}: {
  entry: CodexEntry
  open: boolean
  onOpenChange: (open: boolean) => void
  books?: { id: string; title: string }[]
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{entry.name}</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="details">
          <TabsList className="w-full">
            <TabsTrigger value="details">Details</TabsTrigger>
            <TabsTrigger value="fields">Custom Fields</TabsTrigger>
            <TabsTrigger value="relationships">Relationships</TabsTrigger>
            <TabsTrigger value="image">Image</TabsTrigger>
            <TabsTrigger value="arcs">Arc States</TabsTrigger>
          </TabsList>

          <TabsContent value="details">
            <DetailsTab entry={entry} />
          </TabsContent>
          <TabsContent value="fields">
            <CustomFieldsTab entry={entry} />
          </TabsContent>
          <TabsContent value="relationships">
            <RelationshipsTab entry={entry} />
          </TabsContent>
          <TabsContent value="image">
            <ImageTab entry={entry} />
          </TabsContent>
          <TabsContent value="arcs">
            <ArcStatesTab entry={entry} books={books} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

// ── Details ──────────────────────────────────────────────────────────────

function DetailsTab({ entry }: { entry: CodexEntry }) {
  const updateCodex = useUpdateCodex()
  const [name, setName] = useState(entry.name)
  const [summary, setSummary] = useState(entry.summary ?? '')
  const kindVocab = kindVocabFor(entry.entry_type)
  const [kindValue, setKindValue] = useState<string>(
    kindVocab ? String(entry.custom_fields?.[kindVocab.key] ?? '') : '',
  )
  const [traits, setTraits] = useState<string[]>(
    Array.isArray(entry.custom_fields?.traits)
      ? (entry.custom_fields.traits as unknown[]).map((value) => String(value))
      : [],
  )

  useEffect(() => {
    setName(entry.name)
    setSummary(entry.summary ?? '')
    setKindValue(kindVocab ? String(entry.custom_fields?.[kindVocab.key] ?? '') : '')
    setTraits(
      Array.isArray(entry.custom_fields?.traits)
        ? (entry.custom_fields.traits as unknown[]).map((value) => String(value))
        : [],
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry.id])

  const nameInvalid = name.trim().length === 0

  function toggleTrait(value: string) {
    setTraits((current) =>
      current.includes(value) ? current.filter((trait) => trait !== value) : [...current, value],
    )
  }

  function handleSave() {
    if (nameInvalid) return
    const nextFields: Record<string, unknown> = { ...(entry.custom_fields ?? {}) }
    if (kindVocab) {
      if (kindValue) nextFields[kindVocab.key] = kindValue
      else delete nextFields[kindVocab.key]
    }
    if (entry.entry_type === 'character') {
      nextFields.traits = traits
    }
    updateCodex.mutate({
      id: entry.id,
      name: name.trim(),
      summary: summary.trim() || null,
      custom_fields: nextFields,
    })
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="codex-detail-name">Name</Label>
        <Input
          id="codex-detail-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-invalid={nameInvalid}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="codex-detail-summary">Summary</Label>
        <Textarea
          id="codex-detail-summary"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="Summary (optional)"
          className="min-h-20"
        />
      </div>

      {kindVocab && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="codex-detail-kind">{kindVocab.label}</Label>
          <Select value={kindValue} onValueChange={setKindValue}>
            <SelectTrigger id="codex-detail-kind" className="w-full">
              <SelectValue placeholder={`Choose a ${kindVocab.label.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              {kindVocab.options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {entry.entry_type === 'character' && (
        <div className="flex flex-col gap-1.5">
          <Label>Traits</Label>
          <div className="flex flex-wrap gap-1.5">
            {CHARACTER_TRAITS.map((trait) => {
              const active = traits.includes(trait.value)
              return (
                <Badge
                  key={trait.value}
                  variant={active ? 'default' : 'outline'}
                  role="button"
                  tabIndex={0}
                  aria-pressed={active}
                  className="cursor-pointer select-none"
                  onClick={() => toggleTrait(trait.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      toggleTrait(trait.value)
                    }
                  }}
                >
                  {trait.label}
                </Badge>
              )
            })}
          </div>
        </div>
      )}

      <Button
        onClick={handleSave}
        disabled={nameInvalid || updateCodex.isPending}
        className="self-start"
      >
        Save
      </Button>
    </div>
  )
}

// ── Custom Fields ────────────────────────────────────────────────────────

function customFieldsToRows(customFields: Record<string, unknown> | null): CustomFieldRow[] {
  return Object.entries(customFields ?? {})
    .filter(([key]) => !isManagedKey(key))
    .map(([key, value]) => ({ key, value: value == null ? '' : String(value) }))
}

function CustomFieldsTab({ entry }: { entry: CodexEntry }) {
  const updateCodex = useUpdateCodex()
  const [rows, setRows] = useState<CustomFieldRow[]>(() => customFieldsToRows(entry.custom_fields))

  useEffect(() => {
    setRows(customFieldsToRows(entry.custom_fields))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry.id])

  function updateRow(index: number, patch: Partial<CustomFieldRow>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  function removeRow(index: number) {
    setRows((current) => current.filter((_, i) => i !== index))
  }

  function addRow() {
    setRows((current) => [...current, { key: '', value: '' }])
  }

  function handleSave() {
    const managed: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(entry.custom_fields ?? {})) {
      if (isManagedKey(key)) managed[key] = value
    }
    const nextFields: Record<string, unknown> = { ...managed }
    for (const row of rows) {
      const key = row.key.trim()
      if (!key || isManagedKey(key)) continue
      nextFields[key] = row.value
    }
    updateCodex.mutate({ id: entry.id, custom_fields: nextFields })
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <ScrollArea className="max-h-72">
        <div className="flex flex-col gap-2 pr-2">
          {rows.length === 0 && (
            <p className="text-sm text-muted-foreground">No custom fields yet.</p>
          )}
          {rows.map((row, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                aria-label="Field name"
                placeholder="Field name"
                value={row.key}
                onChange={(event) => updateRow(index, { key: event.target.value })}
                className="flex-1"
              />
              <Input
                aria-label="Field value"
                placeholder="Value"
                value={row.value}
                onChange={(event) => updateRow(index, { value: event.target.value })}
                className="flex-1"
              />
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Remove field"
                onClick={() => removeRow(index)}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </ScrollArea>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={addRow}>
          <Plus className="size-3.5" />
          Add field
        </Button>
        <Button size="sm" onClick={handleSave} disabled={updateCodex.isPending}>
          Save
        </Button>
      </div>
    </div>
  )
}

// ── Relationships ─────────────────────────────────────────────────────────

function RelationshipsTab({ entry }: { entry: CodexEntry }) {
  const { data: relationships, isLoading } = useCodexRelationships(entry.id)
  const { data: allEntries } = useCodexEntries()
  const createRelationship = useCreateRelationship()
  const deleteRelationship = useDeleteRelationship()

  const candidates = (allEntries ?? []).filter((candidate) => candidate.id !== entry.id)
  const [targetId, setTargetId] = useState('')
  const [relType, setRelType] = useState('')
  const [description, setDescription] = useState('')

  function nameFor(id: string): string {
    return (allEntries ?? []).find((candidate) => candidate.id === id)?.name ?? id
  }

  function handleAdd() {
    if (!targetId || !relType) return
    createRelationship.mutate(
      {
        entryId: entry.id,
        to_entry_id: targetId,
        relationship_type: relType,
        description: description.trim() || null,
      },
      {
        onSuccess: () => {
          setTargetId('')
          setRelType('')
          setDescription('')
        },
      },
    )
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <ScrollArea className="max-h-56">
        <div className="flex flex-col gap-2 pr-2">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (relationships ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No relationships yet.</p>
          ) : (
            (relationships ?? []).map((relationship) => {
              const otherId =
                relationship.from_entry_id === entry.id
                  ? relationship.to_entry_id
                  : relationship.from_entry_id
              return (
                <div
                  key={relationship.id}
                  className="flex items-start gap-2 rounded-lg border border-border p-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">
                      {labelFor(RELATIONSHIP_TYPES, relationship.relationship_type)} —{' '}
                      {nameFor(otherId)}
                    </p>
                    {relationship.description && (
                      <p className="text-xs text-muted-foreground">{relationship.description}</p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Remove relationship"
                    disabled={deleteRelationship.isPending}
                    onClick={() =>
                      deleteRelationship.mutate({ relId: relationship.id, entryId: entry.id })
                    }
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              )
            })
          )}
        </div>
      </ScrollArea>

      <Separator />

      <div className="flex flex-col gap-2">
        <Label>Add relationship</Label>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={targetId} onValueChange={setTargetId}>
            <SelectTrigger aria-label="Target entry" className="min-w-40 flex-1">
              <SelectValue placeholder="Entry" />
            </SelectTrigger>
            <SelectContent>
              {candidates.map((candidate) => (
                <SelectItem key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={relType} onValueChange={setRelType}>
            <SelectTrigger aria-label="Relationship type" className="min-w-40 flex-1">
              <SelectValue placeholder="Relationship" />
            </SelectTrigger>
            <SelectContent>
              {RELATIONSHIP_TYPES.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Input
          aria-label="Relationship description (optional)"
          placeholder="Description (optional)"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <Button
          size="sm"
          className="self-start"
          disabled={!targetId || !relType || createRelationship.isPending}
          onClick={handleAdd}
        >
          <Plus className="size-3.5" />
          Add
        </Button>
      </div>
    </div>
  )
}

// ── Image ────────────────────────────────────────────────────────────────

function ImageTab({ entry }: { entry: CodexEntry }) {
  const uploadImage = useUploadImage()
  const attachImage = useUpdateCodex()

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const uploaded = await uploadImage.mutateAsync({ file })
    attachImage.mutate({ id: entry.id, primary_image_id: uploaded.id })
  }

  function handleRemove() {
    attachImage.mutate({ id: entry.id, primary_image_id: null })
  }

  const busy = uploadImage.isPending || attachImage.isPending

  return (
    <div className="flex flex-col gap-3 py-2">
      {entry.primary_image_id ? (
        <div className="flex flex-col gap-2">
          <img
            src={imageUrl(entry.primary_image_id)}
            alt={entry.name}
            className="max-h-64 w-fit max-w-full rounded-lg border border-border object-contain"
          />
          <Button
            variant="secondary"
            size="sm"
            className="self-start"
            onClick={handleRemove}
            disabled={busy}
          >
            <X className="size-3.5" />
            Remove image
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No image attached yet.</p>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="codex-image-upload">
          {entry.primary_image_id ? 'Replace image' : 'Upload image'}
        </Label>
        <Input
          id="codex-image-upload"
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          disabled={busy}
        />
        {busy && (
          <p className="text-xs text-muted-foreground">
            <ImagePlus className="mr-1 inline size-3" />
            Uploading…
          </p>
        )}
      </div>
    </div>
  )
}

// ── Arc States ───────────────────────────────────────────────────────────

function ArcStatesTab({
  entry,
  books,
}: {
  entry: CodexEntry
  books?: { id: string; title: string }[]
}) {
  const { data: fetchedBooks } = useBooks()
  const bookOptions = books ?? fetchedBooks ?? []

  const { data: arcStates, isLoading } = useCodexArcStates(entry.id)
  const createArcState = useCreateArcState()
  const deleteArcState = useDeleteArcState()

  const [bookId, setBookId] = useState('')
  const [orderIndex, setOrderIndex] = useState('0')
  const [statusSummary, setStatusSummary] = useState('')

  function bookTitleFor(id: string): string {
    return bookOptions.find((book) => book.id === id)?.title ?? id
  }

  function handleAdd() {
    const parsedIndex = Number.parseInt(orderIndex, 10)
    if (!bookId || Number.isNaN(parsedIndex) || parsedIndex < 0) return
    createArcState.mutate(
      {
        entryId: entry.id,
        book_id: bookId,
        as_of_outline_order_index: parsedIndex,
        status_summary: statusSummary.trim() || null,
      },
      {
        onSuccess: () => {
          setStatusSummary('')
        },
      },
    )
  }

  return (
    <div className="flex flex-col gap-3 py-2">
      <p className="text-xs text-muted-foreground">
        Arc states are point-in-time; only states at or before a scene's outline position
        inform that scene (anti-spoiler).
      </p>

      <ScrollArea className="max-h-56">
        <div className="flex flex-col gap-2 pr-2">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (arcStates ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No arc states recorded yet.</p>
          ) : (
            (arcStates ?? []).map((arcState) => (
              <div
                key={arcState.id}
                className="flex items-start gap-2 rounded-lg border border-border p-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    {bookTitleFor(arcState.book_id)} @ index {arcState.as_of_outline_order_index}
                  </p>
                  {arcState.status_summary && (
                    <p className="text-xs text-muted-foreground">{arcState.status_summary}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Remove arc state"
                  disabled={deleteArcState.isPending}
                  onClick={() =>
                    deleteArcState.mutate({
                      arcStateId: arcState.id,
                      entryId: entry.id,
                      bookId: arcState.book_id,
                    })
                  }
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>

      <Separator />

      <div className="flex flex-col gap-2">
        <Label>Add arc state</Label>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={bookId} onValueChange={setBookId}>
            <SelectTrigger aria-label="Book" className="min-w-40 flex-1">
              <SelectValue placeholder="Book" />
            </SelectTrigger>
            <SelectContent>
              {bookOptions.map((book) => (
                <SelectItem key={book.id} value={book.id}>
                  {book.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex min-w-40 flex-1 flex-col gap-1.5">
            <Label htmlFor="codex-arc-index" className="text-xs">
              Outline position (index)
            </Label>
            <Input
              id="codex-arc-index"
              type="number"
              min={0}
              value={orderIndex}
              onChange={(event) => setOrderIndex(event.target.value)}
            />
          </div>
        </div>
        <Textarea
          aria-label="Status summary"
          placeholder="Status summary"
          value={statusSummary}
          onChange={(event) => setStatusSummary(event.target.value)}
          className="min-h-16"
        />
        <Button
          size="sm"
          className="self-start"
          disabled={!bookId || createArcState.isPending}
          onClick={handleAdd}
        >
          <Plus className="size-3.5" />
          Add
        </Button>
      </div>
    </div>
  )
}

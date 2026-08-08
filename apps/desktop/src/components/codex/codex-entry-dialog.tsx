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
import { SearchCombobox } from '@/components/ui/search-combobox'
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
 * dialog (Details tab's guided Role/Kind combobox and traits editor, or the backend's
 * arc-state bookkeeping) — excluded from the free-form Custom Fields editor so users
 * can't fight the guided UI. */
const MANAGED_KEYS = new Set(['role', 'kind', 'traits'])
function isManagedKey(key: string): boolean {
  return MANAGED_KEYS.has(key) || key.startsWith('arc_')
}

/** The kind-vocab options for this entry's `entry_type` — none for object types without one
 * (there are none currently, but keep this shape future-proof). The stored value is NOT
 * restricted to these options (see the creatable `SearchCombobox` in `DetailsTab`); this
 * only supplies the guided preset list. */
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

/** Short badge text for an entry's type, shown next to its name in the relationship
 * target picker so entries of every Codex type are distinguishable at a glance. */
const ENTRY_TYPE_BADGE: Record<CodexEntry['entry_type'], string> = {
  character: 'character',
  location: 'location',
  faction: 'faction',
  object_lore: 'lore',
}

interface CustomFieldRow {
  key: string
  value: string
}

/**
 * The full Codex entity editor (docs/06-ROADMAP.md Phase 3 task FE-7). Opened from
 * `CodexPanel` (FE-8 wires the trigger) with one existing entry. Three tabs: Details (a
 * wide two-column view — name/description/role-or-kind/traits on the left, Relationships
 * and Arc-over-time stacked on the right, so no tab-hopping is needed to cross-reference
 * them while editing), Custom Fields, Image.
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
      <DialogContent className="max-h-[85vh] max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{entry.name}</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="details">
          <TabsList className="w-full">
            <TabsTrigger value="details">Details</TabsTrigger>
            <TabsTrigger value="fields">Custom Fields</TabsTrigger>
            <TabsTrigger value="image">Image</TabsTrigger>
          </TabsList>

          <TabsContent value="details">
            <div className="grid gap-6 sm:grid-cols-2">
              <DetailsTab entry={entry} />
              <div className="flex flex-col gap-4 py-2">
                <RelationshipsSection entry={entry} />
                <Separator />
                <ArcSection entry={entry} books={books} />
              </div>
            </div>
          </TabsContent>
          <TabsContent value="fields">
            <CustomFieldsTab entry={entry} />
          </TabsContent>
          <TabsContent value="image">
            <ImageTab entry={entry} />
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
  const [customTraitInput, setCustomTraitInput] = useState('')

  useEffect(() => {
    setName(entry.name)
    setSummary(entry.summary ?? '')
    setKindValue(kindVocab ? String(entry.custom_fields?.[kindVocab.key] ?? '') : '')
    setTraits(
      Array.isArray(entry.custom_fields?.traits)
        ? (entry.custom_fields.traits as unknown[]).map((value) => String(value))
        : [],
    )
    setCustomTraitInput('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry.id])

  const nameInvalid = name.trim().length === 0
  const presetTraitValues = new Set(
    CHARACTER_TRAITS.map((trait) => trait.value.toLowerCase()),
  )
  const customTraits = traits.filter((trait) => !presetTraitValues.has(trait.toLowerCase()))

  function toggleTrait(value: string) {
    setTraits((current) =>
      current.includes(value) ? current.filter((trait) => trait !== value) : [...current, value],
    )
  }

  function addCustomTrait() {
    const value = customTraitInput.trim()
    if (!value) return
    const normalized = value.toLowerCase()
    // Case-insensitive dedupe against both the preset trait vocab and whatever's already
    // selected — "Brave" while "brave" is selected (preset or a prior custom trait) should
    // be a no-op, not a near-duplicate chip. Preserve the typed casing only when it's genuinely new.
    const isDuplicate =
      presetTraitValues.has(normalized) ||
      traits.some((trait) => trait.toLowerCase() === normalized)
    if (!isDuplicate) {
      setTraits((current) => [...current, value])
    }
    setCustomTraitInput('')
  }

  function removeTrait(value: string) {
    setTraits((current) => current.filter((trait) => trait !== value))
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
        <Label htmlFor="codex-detail-summary">Description</Label>
        <Textarea
          id="codex-detail-summary"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          placeholder="Description (optional)"
          className="min-h-20"
        />
      </div>

      {kindVocab && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="codex-detail-kind">{kindVocab.label}</Label>
          <SearchCombobox
            id="codex-detail-kind"
            value={kindValue}
            onValueChange={setKindValue}
            options={kindVocab.options.map((option) => ({
              value: option.value,
              label: option.label,
              sublabel: option.hint,
            }))}
            placeholder={`Choose a ${kindVocab.label.toLowerCase()}`}
            searchPlaceholder={`Search or type a ${kindVocab.label.toLowerCase()}…`}
            allowCustomValue
            triggerAriaLabel={kindVocab.label}
          />
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
            {customTraits.map((trait) => (
              <Badge key={trait} variant="default" className="gap-1 py-0.5 pr-1">
                {trait}
                <button
                  type="button"
                  aria-label={`Remove trait ${trait}`}
                  onClick={() => removeTrait(trait)}
                  className="rounded-full p-0.5 hover:bg-primary-foreground/20 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Input
              aria-label="Add a custom trait"
              placeholder="Add a custom trait"
              value={customTraitInput}
              onChange={(event) => setCustomTraitInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  addCustomTrait()
                }
              }}
              className="h-8 flex-1"
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={addCustomTrait}
              disabled={!customTraitInput.trim()}
            >
              <Plus className="size-3.5" />
              Add
            </Button>
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
// Rendered inside the Details tab's right-hand column (not its own tab) — see
// `CodexEntryDialog` above. `candidates` intentionally spans every Codex entry type (not
// just this entry's own type), matching how relationships already worked pre-redesign.

function RelationshipsSection({ entry }: { entry: CodexEntry }) {
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
          <SearchCombobox
            value={targetId}
            onValueChange={setTargetId}
            options={candidates.map((candidate) => ({
              value: candidate.id,
              label: candidate.name,
              badge: ENTRY_TYPE_BADGE[candidate.entry_type],
            }))}
            placeholder="Entry"
            searchPlaceholder="Search entries…"
            emptyMessage="No other entries yet."
            triggerAriaLabel="Target entry"
            className="min-w-40 flex-1"
          />
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

// ── Arc over time ────────────────────────────────────────────────────────
// Rendered inside the Details tab's right-hand column (not its own tab) — see
// `CodexEntryDialog` above.

function ArcSection({
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
      <div className="flex flex-col gap-1">
        <Label className="text-sm font-semibold">Arc over time</Label>
        <p className="text-xs text-muted-foreground">
          A spoiler-safe timeline of how this entry changes across the story. Each note only
          reaches the AI for scenes at or after that story position, so later twists never
          leak into earlier scenes.
        </p>
      </div>

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

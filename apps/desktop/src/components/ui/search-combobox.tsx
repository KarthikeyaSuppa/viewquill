import { useEffect, useId, useRef, useState } from 'react'
import { Check, ChevronsUpDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

export interface SearchComboboxOption {
  value: string
  label: string
  /** Optional secondary line under `label` (e.g. a vocab hint). */
  sublabel?: string
  /** Optional short badge rendered at the row's end (e.g. an entry type). */
  badge?: string
}

/** One row of the rendered/keyboard-navigable list: either the creatable "Use ..." row
 * or a preset option. Kept as a single flat list so arrow-key navigation and
 * `aria-activedescendant` only ever have to reason about one index. */
type ComboboxRow =
  | { kind: 'custom'; value: string }
  | { kind: 'option'; option: SearchComboboxOption }

/**
 * A lightweight searchable (optionally creatable) combobox built entirely from this app's
 * own `Popover`/`Input`/`ScrollArea`/`Badge`/`Button` primitives — no `cmdk` dependency.
 *
 * Two call sites in `codex-entry-dialog.tsx`:
 *  - a creatable Role/Kind picker (`allowCustomValue`) where any typed string is a valid
 *    value, not just one of the preset `options`;
 *  - a searchable relationship-target picker (large `options` list, type-to-filter, no
 *    free text) where each row also shows a type `badge`.
 *
 * Purely a controlled `value`/`onValueChange` pair — same contract as this codebase's
 * `Select`, so it drops in without changing any surrounding save/mutation logic.
 *
 * Keyboard/ARIA: follows the combobox-with-listbox-popup pattern — the search `Input`
 * keeps DOM focus the whole time; ArrowUp/ArrowDown move a highlighted-row index and
 * `aria-activedescendant` points the assistive-tech cursor at it, Enter commits the
 * highlighted row (including the creatable "Use ..." row), Escape closes (handled by
 * Radix `Popover` already).
 */
export function SearchCombobox({
  value,
  onValueChange,
  options,
  placeholder = 'Select…',
  searchPlaceholder = 'Search…',
  emptyMessage = 'No matches.',
  allowCustomValue = false,
  customValueLabel,
  triggerAriaLabel,
  ariaLabel,
  className,
  id,
}: {
  value: string
  onValueChange: (value: string) => void
  options: SearchComboboxOption[]
  placeholder?: string
  searchPlaceholder?: string
  emptyMessage?: string
  /** When true, typing a value that doesn't match any option shows a "Use ..." row that
   * stores the raw typed string instead of a preset option's value. */
  allowCustomValue?: boolean
  customValueLabel?: (typed: string) => string
  triggerAriaLabel?: string
  /** Accessible label for the search input. Defaults to `searchPlaceholder` so existing
   * call sites (which only set `searchPlaceholder`) get a sensible label for free. */
  ariaLabel?: string
  className?: string
  id?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([])

  const generatedId = useId()
  const listboxId = `${generatedId}-listbox`

  const selected = options.find((option) => option.value === value)
  const triggerText = selected ? selected.label : value ? value : placeholder

  const query = search.trim().toLowerCase()
  const filtered = query
    ? options.filter(
        (option) =>
          option.label.toLowerCase().includes(query) ||
          option.sublabel?.toLowerCase().includes(query) ||
          option.value.toLowerCase().includes(query),
      )
    : options

  const trimmed = search.trim()
  const showCustomRow =
    allowCustomValue &&
    trimmed.length > 0 &&
    !options.some((option) => option.value.toLowerCase() === trimmed.toLowerCase())

  const rows: ComboboxRow[] = [
    ...(showCustomRow ? [{ kind: 'custom' as const, value: trimmed }] : []),
    ...filtered.map((option) => ({ kind: 'option' as const, option })),
  ]

  // Reset the highlight to the first row whenever the filter text changes (or the popover
  // opens/closes), so a previous highlight never survives into a differently-filtered list.
  useEffect(() => {
    setHighlightedIndex(0)
  }, [search, open])

  useEffect(() => {
    if (!open) return
    optionRefs.current[highlightedIndex]?.scrollIntoView({ block: 'nearest' })
  }, [highlightedIndex, open])

  function choose(nextValue: string) {
    onValueChange(nextValue)
    setOpen(false)
    setSearch('')
  }

  function commitHighlighted() {
    const row = rows[highlightedIndex]
    if (row) {
      choose(row.kind === 'custom' ? row.value : row.option.value)
      return
    }
    // Defensive fallback: nothing is highlighted (e.g. an empty list) but the typed text is
    // still a valid custom value — Enter should still be able to create it.
    if (allowCustomValue && trimmed.length > 0) {
      choose(trimmed)
    }
  }

  function handleSearchKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlightedIndex((current) =>
        rows.length === 0 ? 0 : Math.min(current + 1, rows.length - 1),
      )
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightedIndex((current) => (rows.length === 0 ? 0 : Math.max(current - 1, 0)))
    } else if (event.key === 'Enter') {
      event.preventDefault()
      commitHighlighted()
    }
  }

  const activeRow = rows[highlightedIndex]
  const activeDescendantId =
    open && activeRow
      ? activeRow.kind === 'custom'
        ? `${listboxId}-option-custom`
        : `${listboxId}-option-${activeRow.option.value}`
      : undefined

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen)
        if (!nextOpen) setSearch('')
      }}
    >
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-controls={listboxId}
          aria-label={triggerAriaLabel}
          className={cn(
            'w-full justify-between font-normal',
            !selected && !value && 'text-muted-foreground',
            className,
          )}
        >
          <span className="truncate">{triggerText}</span>
          <ChevronsUpDown className="size-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-2">
        <Input
          autoFocus
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          onKeyDown={handleSearchKeyDown}
          placeholder={searchPlaceholder}
          aria-label={ariaLabel ?? searchPlaceholder}
          role="combobox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-activedescendant={activeDescendantId}
          aria-autocomplete="list"
          className="mb-2"
        />
        <ScrollArea className="max-h-56">
          <div
            id={listboxId}
            role="listbox"
            aria-label={ariaLabel ?? searchPlaceholder}
            className="flex flex-col gap-0.5 pr-1"
          >
            {showCustomRow && (
              <button
                id={`${listboxId}-option-custom`}
                ref={(el) => {
                  optionRefs.current[0] = el
                }}
                type="button"
                role="option"
                aria-selected={false}
                onClick={() => choose(trimmed)}
                onMouseEnter={() => setHighlightedIndex(0)}
                className={cn(
                  'flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-primary hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                  highlightedIndex === 0 && 'bg-accent text-accent-foreground',
                )}
              >
                {customValueLabel ? customValueLabel(trimmed) : `Use "${trimmed}"`}
              </button>
            )}
            {filtered.length === 0 && !showCustomRow ? (
              <p className="px-2 py-1.5 text-xs text-muted-foreground">{emptyMessage}</p>
            ) : (
              filtered.map((option, filteredIndex) => {
                const rowIndex = (showCustomRow ? 1 : 0) + filteredIndex
                const highlighted = highlightedIndex === rowIndex
                return (
                  <button
                    key={option.value}
                    id={`${listboxId}-option-${option.value}`}
                    ref={(el) => {
                      optionRefs.current[rowIndex] = el
                    }}
                    type="button"
                    role="option"
                    aria-selected={option.value === value}
                    onClick={() => choose(option.value)}
                    onMouseEnter={() => setHighlightedIndex(rowIndex)}
                    className={cn(
                      'flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                      highlighted && 'bg-accent text-accent-foreground',
                    )}
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate">{option.label}</span>
                      {option.sublabel && (
                        <span className="truncate text-xs text-muted-foreground">
                          {option.sublabel}
                        </span>
                      )}
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {option.badge && (
                        <Badge variant="outline" className="text-[10px]">
                          {option.badge}
                        </Badge>
                      )}
                      {option.value === value && <Check className="size-3.5" />}
                    </span>
                  </button>
                )
              })
            )}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}

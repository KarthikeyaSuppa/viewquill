import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { FONT_STACKS, READING_DEFAULTS } from '@/lib/apply-settings'
import { cn } from '@/lib/utils'

/** Same short passage everywhere a font/spacing preview is shown (wizard + settings). */
export const SAMPLE_PASSAGE =
  'The quill dipped low over the page, and for a moment the whole story seemed to hold its breath before the ink began to flow.'

export const FONT_OPTIONS: { value: string; label: string; note?: string }[] = [
  { value: 'Lexend', label: 'Lexend', note: 'Recommended default' },
  { value: 'Atkinson Hyperlegible Next', label: 'Atkinson Hyperlegible Next' },
  { value: 'OpenDyslexic', label: 'OpenDyslexic' },
  { value: 'Inter', label: 'Inter' },
  { value: 'System Serif', label: 'System Serif' },
]

export interface ReadingControlsValue {
  font_family: string
  font_size: number
  line_height: number
  letter_spacing: number
  line_length_ch: number
}

interface ReadingControlsProps {
  value: ReadingControlsValue
  onChange: (value: ReadingControlsValue) => void
  /** Fires once per interaction (pointer-up), for callers that persist on commit rather than per-tick. */
  onCommit?: (value: ReadingControlsValue) => void
  className?: string
}

interface LabeledSliderProps {
  id: string
  label: string
  value: number
  min: number
  max: number
  step: number
  defaultValue: number
  formatValue: (value: number) => string
  onValueChange: (value: number) => void
  onValueCommit?: (value: number) => void
}

/** A single BDA-range slider: numeric readout + a tick marking the evidence-backed default. */
function LabeledSlider({
  id,
  label,
  value,
  min,
  max,
  step,
  defaultValue,
  formatValue,
  onValueChange,
  onValueCommit,
}: LabeledSliderProps) {
  const defaultPct = ((defaultValue - min) / (max - min)) * 100

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor={id}>{label}</Label>
        <span className="text-sm text-muted-foreground tabular-nums">{formatValue(value)}</span>
      </div>
      <div className="relative pt-2.5">
        <span
          aria-hidden="true"
          title={`BDA default: ${formatValue(defaultValue)}`}
          className="absolute top-0 h-1.5 w-px -translate-x-1/2 bg-muted-foreground/50"
          style={{ left: `${defaultPct}%` }}
        />
        <Slider
          id={id}
          value={[value]}
          min={min}
          max={max}
          step={step}
          onValueChange={([next]) => onValueChange(next)}
          onValueCommit={onValueCommit ? ([next]) => onValueCommit(next) : undefined}
        />
      </div>
    </div>
  )
}

/**
 * The reusable Reading Comfort controls block (docs/10 §2, §7): font family + the four
 * BDA-range sliders, with a live `.manuscript` preview driven from local draft state (not
 * just the global `--reading-*` vars) so dragging feels instant. Used by both the
 * first-run wizard and the Settings screen.
 */
export function ReadingControls({ value, onChange, onCommit, className }: ReadingControlsProps) {
  function patch(partial: Partial<ReadingControlsValue>) {
    onChange({ ...value, ...partial })
  }
  function patchCommit(partial: Partial<ReadingControlsValue>) {
    onCommit?.({ ...value, ...partial })
  }

  return (
    <div className={cn('space-y-5', className)}>
      <div className="space-y-1.5">
        <Label htmlFor="reading-font-family">Font</Label>
        <Select
          value={value.font_family}
          onValueChange={(next) => {
            patch({ font_family: next })
            patchCommit({ font_family: next })
          }}
        >
          <SelectTrigger id="reading-font-family" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FONT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
                {opt.note ? ` — ${opt.note}` : ''}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <LabeledSlider
        id="reading-font-size"
        label="Font size"
        value={value.font_size}
        min={16}
        max={28}
        step={1}
        defaultValue={READING_DEFAULTS.font_size}
        formatValue={(v) => `${v}px`}
        onValueChange={(v) => patch({ font_size: v })}
        onValueCommit={(v) => patchCommit({ font_size: v })}
      />

      <LabeledSlider
        id="reading-letter-spacing"
        label="Letter spacing"
        value={value.letter_spacing}
        min={0}
        max={0.12}
        step={0.005}
        defaultValue={READING_DEFAULTS.letter_spacing}
        formatValue={(v) => `${v.toFixed(3)}em`}
        onValueChange={(v) => patch({ letter_spacing: v })}
        onValueCommit={(v) => patchCommit({ letter_spacing: v })}
      />

      <LabeledSlider
        id="reading-line-height"
        label="Line height"
        value={value.line_height}
        min={1.2}
        max={2.0}
        step={0.1}
        defaultValue={READING_DEFAULTS.line_height}
        formatValue={(v) => v.toFixed(1)}
        onValueChange={(v) => patch({ line_height: v })}
        onValueCommit={(v) => patchCommit({ line_height: v })}
      />

      <LabeledSlider
        id="reading-line-length"
        label="Line length"
        value={value.line_length_ch}
        min={45}
        max={80}
        step={1}
        defaultValue={READING_DEFAULTS.line_length_ch}
        formatValue={(v) => `${v}ch`}
        onValueChange={(v) => patch({ line_length_ch: v })}
        onValueCommit={(v) => patchCommit({ line_length_ch: v })}
      />

      <p
        className="manuscript rounded-xl p-4 text-sm"
        style={{
          fontFamily: FONT_STACKS[value.font_family] ?? FONT_STACKS[READING_DEFAULTS.font_family],
          fontSize: `${value.font_size}px`,
          lineHeight: value.line_height,
          letterSpacing: `${value.letter_spacing}em`,
          wordSpacing: `${value.letter_spacing * 3.5}em`,
          maxWidth: `${value.line_length_ch}ch`,
        }}
      >
        {SAMPLE_PASSAGE}
      </p>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Separator } from '@/components/ui/separator'
import { ReadingControls, type ReadingControlsValue } from '@/components/reading-controls'
import { READING_DEFAULTS, type DelightLevel } from '@/lib/apply-settings'
import { useSettings, useUpdateSettings } from '@/queries/settings'
import { useOnboardingWizardStore } from '@/stores/onboarding'
import { cn } from '@/lib/utils'

type ThemeMode = 'day' | 'night' | 'auto'

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'day', label: 'Day' },
  { value: 'night', label: 'Night' },
  { value: 'auto', label: 'Auto (by local time)' },
]

const DELIGHT_OPTIONS: { value: DelightLevel; label: string }[] = [
  { value: 'calm', label: 'Calm' },
  { value: 'standard', label: 'Standard' },
  { value: 'playful', label: 'Playful' },
]

/** Settings screen (docs/10 §7): Reading Comfort controls + theme/delight, all applying live. */
export function SettingsScreen() {
  const { data: values } = useSettings()
  const updateSettings = useUpdateSettings()
  const openWizard = useOnboardingWizardStore((s) => s.open)

  const [reading, setReading] = useState<ReadingControlsValue>(READING_DEFAULTS)

  // Re-seed local draft whenever fresh settings land (initial load, or after a PATCH elsewhere).
  useEffect(() => {
    if (!values) return
    setReading({
      font_family: typeof values.font_family === 'string' ? values.font_family : READING_DEFAULTS.font_family,
      font_size: typeof values.font_size === 'number' ? values.font_size : READING_DEFAULTS.font_size,
      line_height: typeof values.line_height === 'number' ? values.line_height : READING_DEFAULTS.line_height,
      letter_spacing:
        typeof values.letter_spacing === 'number' ? values.letter_spacing : READING_DEFAULTS.letter_spacing,
      line_length_ch:
        typeof values.line_length_ch === 'number' ? values.line_length_ch : READING_DEFAULTS.line_length_ch,
    })
  }, [values])

  const themeMode: ThemeMode =
    values?.theme_mode === 'day' || values?.theme_mode === 'night' || values?.theme_mode === 'auto'
      ? values.theme_mode
      : 'night'
  const delightLevel: DelightLevel =
    values?.delight_level === 'calm' || values?.delight_level === 'standard' ? values.delight_level : 'playful'

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Every change here applies live.</p>
      </div>

      <section className="glass glass-edge space-y-5 rounded-2xl p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-medium">Reading Comfort</h2>
            <p className="text-sm text-muted-foreground">
              Font, spacing, and layout for the manuscript surface (docs/10 §2).
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={openWizard}>
            Re-run wizard
          </Button>
        </div>

        <ReadingControls
          value={reading}
          onChange={setReading}
          onCommit={(next) => updateSettings.mutate({ ...next })}
        />
      </section>

      <section className="glass glass-edge space-y-3 rounded-2xl p-5">
        <h2 className="text-base font-medium">Theme</h2>
        <RadioGroup
          value={themeMode}
          onValueChange={(v: ThemeMode) => updateSettings.mutate({ theme_mode: v })}
          className="flex flex-wrap gap-2"
        >
          {THEME_OPTIONS.map((opt) => {
            const id = `settings-theme-${opt.value}`
            return (
              <label
                key={opt.value}
                htmlFor={id}
                className={cn(
                  'flex cursor-pointer items-center gap-2 rounded-xl border border-border px-3 py-2 transition-colors hover:bg-accent/50',
                  themeMode === opt.value && 'border-primary bg-primary/5 ring-1 ring-primary/30',
                )}
              >
                <RadioGroupItem value={opt.value} id={id} />
                <Label htmlFor={id} className="text-sm">
                  {opt.label}
                </Label>
              </label>
            )
          })}
        </RadioGroup>
      </section>

      <section className="glass glass-edge space-y-3 rounded-2xl p-5">
        <h2 className="text-base font-medium">Delight level</h2>
        <p className="text-sm text-muted-foreground">Motion, sounds, mascot, and confetti (docs/10 §8).</p>
        <RadioGroup
          value={delightLevel}
          onValueChange={(v: DelightLevel) => updateSettings.mutate({ delight_level: v })}
          className="flex flex-wrap gap-2"
        >
          {DELIGHT_OPTIONS.map((opt) => {
            const id = `settings-delight-${opt.value}`
            return (
              <label
                key={opt.value}
                htmlFor={id}
                className={cn(
                  'flex cursor-pointer items-center gap-2 rounded-xl border border-border px-3 py-2 transition-colors hover:bg-accent/50',
                  delightLevel === opt.value && 'border-primary bg-primary/5 ring-1 ring-primary/30',
                )}
              >
                <RadioGroupItem value={opt.value} id={id} />
                <Label htmlFor={id} className="text-sm">
                  {opt.label}
                </Label>
              </label>
            )
          })}
        </RadioGroup>
      </section>

      <Separator />
    </div>
  )
}

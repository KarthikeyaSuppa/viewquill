import { useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ReadingControls, FONT_OPTIONS, SAMPLE_PASSAGE, type ReadingControlsValue } from '@/components/reading-controls'
import { applyDelight, applyReadingVars, resolveTheme, FONT_STACKS, READING_DEFAULTS } from '@/lib/apply-settings'
import type { DelightLevel } from '@/lib/apply-settings'
import { useSettings, useUpdateSettings } from '@/queries/settings'
import { useOnboardingWizardStore } from '@/stores/onboarding'
import { useThemeStore, type Theme } from '@/stores/theme'
import { cn } from '@/lib/utils'
import { LottiePlayer } from '@/lib/lottie'

type ThemeMode = Theme | 'auto'

interface WizardDraft extends ReadingControlsValue {
  theme_mode: ThemeMode
  delight_level: DelightLevel
}

function draftFromValues(values: Record<string, unknown> | undefined): WizardDraft {
  return {
    font_family: typeof values?.font_family === 'string' ? values.font_family : READING_DEFAULTS.font_family,
    font_size: typeof values?.font_size === 'number' ? values.font_size : READING_DEFAULTS.font_size,
    line_height: typeof values?.line_height === 'number' ? values.line_height : READING_DEFAULTS.line_height,
    letter_spacing:
      typeof values?.letter_spacing === 'number' ? values.letter_spacing : READING_DEFAULTS.letter_spacing,
    line_length_ch:
      typeof values?.line_length_ch === 'number' ? values.line_length_ch : READING_DEFAULTS.line_length_ch,
    theme_mode:
      values?.theme_mode === 'day' || values?.theme_mode === 'night' || values?.theme_mode === 'auto'
        ? values.theme_mode
        : 'night',
    delight_level:
      values?.delight_level === 'calm' || values?.delight_level === 'standard' ? values.delight_level : 'playful',
  }
}

const STEPS = ['Font', 'Spacing', 'Theme', 'Delight'] as const

const THEME_OPTIONS: { value: ThemeMode; label: string; hint: string }[] = [
  { value: 'day', label: 'Day', hint: 'Warm cream "paper studio" — tuned for long reading sessions.' },
  { value: 'night', label: 'Night', hint: 'Deep charcoal "cinematic studio" — fireflies included.' },
  { value: 'auto', label: 'Auto', hint: 'Night from 6pm–6am local time, Day otherwise.' },
]

const DELIGHT_OPTIONS: { value: DelightLevel; label: string; hint: string }[] = [
  { value: 'calm', label: 'Calm', hint: 'Subtle motion only — no confetti, sounds, or mascot.' },
  { value: 'standard', label: 'Standard', hint: 'Motion + ambient firefly; confetti on major milestones.' },
  { value: 'playful', label: 'Playful', hint: 'Everything — confetti, quiet sounds, a fully animated mascot.' },
]

/**
 * The first-run Reading Comfort Wizard (docs/10 §7). Auto-opened by AppShell when
 * `onboarding_complete !== true` (non-dismissable then); re-openable anytime afterwards
 * from Settings → "Reading Comfort" (dismissable in that case). Every choice applies live
 * as it's made; Finish persists the whole draft plus `onboarding_complete: true`.
 */
export function ReadingComfortWizard() {
  const isOpen = useOnboardingWizardStore((s) => s.isOpen)
  const close = useOnboardingWizardStore((s) => s.close)
  const { data: values } = useSettings()
  const updateSettings = useUpdateSettings()
  const setTheme = useThemeStore((s) => s.setTheme)
  const reduceMotion = useReducedMotion()

  const isFirstRun = values?.onboarding_complete !== true

  const [step, setStep] = useState(0)
  const [draft, setDraft] = useState<WizardDraft>(() => draftFromValues(values))

  // Re-seed the draft from current settings each time the wizard opens.
  useEffect(() => {
    if (isOpen) {
      setDraft(draftFromValues(values))
      setStep(0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  function applyLive(partial: Partial<WizardDraft>) {
    const next = { ...draft, ...partial }
    setDraft(next)
    applyReadingVars(next)
    setTheme(resolveTheme(next.theme_mode))
    applyDelight(next.delight_level)
  }

  function handleOpenChange(next: boolean) {
    if (next) return
    if (isFirstRun) return // non-dismissable on first run — must Finish
    close()
  }

  function handleFinish() {
    updateSettings.mutate({ ...draft, onboarding_complete: true })
    close()
  }

  const isLastStep = step === STEPS.length - 1
  const stepTransition = reduceMotion
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : { initial: { opacity: 0, x: 12 }, animate: { opacity: 1, x: 0 }, exit: { opacity: 0, x: -12 } }

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent
        showCloseButton={!isFirstRun}
        onEscapeKeyDown={(e) => isFirstRun && e.preventDefault()}
        onInteractOutside={(e) => isFirstRun && e.preventDefault()}
        className="glass glass-edge max-w-xl gap-5 sm:max-w-xl"
      >
        <DialogHeader className="flex-row items-center gap-3 space-y-0">
          <LottiePlayer
            animationData={() => import('@/assets/lottie/mascot-idle.json')}
            loop
            ariaHidden
            className="size-12 shrink-0"
          />
          <div className="space-y-1.5">
            <DialogTitle>Reading Comfort Wizard</DialogTitle>
            <DialogDescription>
              Four quick choices, applied live as you make them. Re-run this anytime from Settings.
            </DialogDescription>
          </div>
        </DialogHeader>

        <div className="flex items-center gap-1.5" aria-hidden="true">
          {STEPS.map((label, i) => (
            <div key={label} className={cn('h-1.5 flex-1 rounded-full', i <= step ? 'bg-primary' : 'bg-muted')} />
          ))}
        </div>

        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={step}
            initial={stepTransition.initial}
            animate={stepTransition.animate}
            exit={stepTransition.exit}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="min-h-[320px]"
          >
            {step === 0 && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Tap the one that feels most comfortable to read. Preference isn't always the fastest fit — you
                  can change this anytime.
                </p>
                {/* Full 60s timed self-test (measuring reading speed per font, per docs/10 §2) is a
                    future refinement; this tap-through selection covers the "measure, don't just ask"
                    intent for Phase 1 without the timing instrumentation. */}
                <RadioGroup
                  value={draft.font_family}
                  onValueChange={(v) => applyLive({ font_family: v })}
                  className="max-h-[280px] gap-2.5 overflow-y-auto pr-1"
                >
                  {FONT_OPTIONS.map((opt) => {
                    const id = `wizard-font-${opt.value}`
                    return (
                      <label
                        key={opt.value}
                        htmlFor={id}
                        className={cn(
                          'flex cursor-pointer items-start gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-accent/50',
                          draft.font_family === opt.value && 'border-primary bg-primary/5 ring-1 ring-primary/30',
                        )}
                      >
                        <RadioGroupItem value={opt.value} id={id} className="mt-1" />
                        <div className="flex-1 space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{opt.label}</span>
                            {opt.note && <span className="text-xs text-muted-foreground">{opt.note}</span>}
                          </div>
                          <p
                            className="manuscript rounded-lg px-3 py-2 text-sm"
                            style={{ fontFamily: FONT_STACKS[opt.value] }}
                          >
                            {SAMPLE_PASSAGE}
                          </p>
                        </div>
                      </label>
                    )
                  })}
                </RadioGroup>
              </div>
            )}

            {step === 1 && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Letter spacing has the strongest evidence — start there, then fine-tune the rest.
                </p>
                <ReadingControls value={draft} onChange={(next) => applyLive(next)} />
              </div>
            )}

            {step === 2 && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">Pick a theme — this applies immediately.</p>
                <RadioGroup
                  value={draft.theme_mode}
                  onValueChange={(v: ThemeMode) => applyLive({ theme_mode: v })}
                  className="gap-2.5"
                >
                  {THEME_OPTIONS.map((opt) => {
                    const id = `wizard-theme-${opt.value}`
                    return (
                      <label
                        key={opt.value}
                        htmlFor={id}
                        className={cn(
                          'flex cursor-pointer items-start gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-accent/50',
                          draft.theme_mode === opt.value && 'border-primary bg-primary/5 ring-1 ring-primary/30',
                        )}
                      >
                        <RadioGroupItem value={opt.value} id={id} className="mt-1" />
                        <div className="space-y-0.5">
                          <Label htmlFor={id} className="text-sm font-medium">
                            {opt.label}
                          </Label>
                          <p className="text-xs text-muted-foreground">{opt.hint}</p>
                        </div>
                      </label>
                    )
                  })}
                </RadioGroup>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  How much delight do you want? Every element here stays individually toggleable in Settings.
                </p>
                <RadioGroup
                  value={draft.delight_level}
                  onValueChange={(v: DelightLevel) => applyLive({ delight_level: v })}
                  className="gap-2.5"
                >
                  {DELIGHT_OPTIONS.map((opt) => {
                    const id = `wizard-delight-${opt.value}`
                    return (
                      <label
                        key={opt.value}
                        htmlFor={id}
                        className={cn(
                          'flex cursor-pointer items-start gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-accent/50',
                          draft.delight_level === opt.value && 'border-primary bg-primary/5 ring-1 ring-primary/30',
                        )}
                      >
                        <RadioGroupItem value={opt.value} id={id} className="mt-1" />
                        <div className="space-y-0.5">
                          <Label htmlFor={id} className="text-sm font-medium">
                            {opt.label}
                            {opt.value === 'playful' && (
                              <span className="ml-2 text-xs text-muted-foreground">Default</span>
                            )}
                          </Label>
                          <p className="text-xs text-muted-foreground">{opt.hint}</p>
                        </div>
                      </label>
                    )
                  })}
                </RadioGroup>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

        <div className="flex items-center justify-between pt-1">
          <Button variant="ghost" size="sm" disabled={step === 0} onClick={() => setStep((s) => s - 1)}>
            Back
          </Button>
          {isLastStep ? (
            <Button size="sm" onClick={handleFinish} disabled={updateSettings.isPending}>
              Finish
            </Button>
          ) : (
            <Button size="sm" onClick={() => setStep((s) => s + 1)}>
              Next
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Book,
  Cloud,
  Cpu,
  Eye,
  EyeOff,
  Mic,
  Monitor,
  Palette,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'
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
import { Switch } from '@/components/ui/switch'
import { ReadingControls, type ReadingControlsValue } from '@/components/reading-controls'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import * as keyring from '@/lib/keyring'
import { getLocalVoices } from '@/lib/speech'
import { BG_TINTS, READING_DEFAULTS, type DelightLevel } from '@/lib/apply-settings'
import { useDelight } from '@/lib/delight'
import { useSettings, useUpdateSettings } from '@/queries/settings'
import { useOnboardingWizardStore } from '@/stores/onboarding'
import { cn } from '@/lib/utils'

type ThemeMode = 'day' | 'night' | 'sunset' | 'sunrise' | 'auto'
type AiMode = 'offline' | 'online' | 'hybrid'
type BgTint = keyof typeof BG_TINTS
type SectionId = 'reading' | 'voice' | 'theme' | 'ai' | 'delight'

const BG_TINT_OPTIONS: { value: BgTint; label: string }[] = [
  { value: 'cream', label: 'Cream' },
  { value: 'sand', label: 'Sand' },
  { value: 'peach', label: 'Peach' },
  { value: 'apricot', label: 'Apricot' },
]

const THEME_OPTIONS: { value: ThemeMode; label: string }[] = [
  { value: 'day', label: 'Day' },
  { value: 'night', label: 'Night' },
  { value: 'sunset', label: 'Sunset' },
  { value: 'sunrise', label: 'Sunrise' },
  { value: 'auto', label: 'Auto (by local time)' },
]

const DELIGHT_OPTIONS: { value: DelightLevel; label: string }[] = [
  { value: 'calm', label: 'Calm' },
  { value: 'standard', label: 'Standard' },
  { value: 'playful', label: 'Playful' },
]

// AI mode copy per docs/08-AI-PROVIDER-MODES.md "The three modes".
const AI_MODE_OPTIONS: { value: AiMode; label: string; description: string }[] = [
  { value: 'offline', label: 'Offline', description: 'Local model only. Zero network calls, ever.' },
  { value: 'online', label: 'Online', description: 'GroqCloud only, using your own free API key.' },
  {
    value: 'hybrid',
    label: 'Hybrid',
    description: 'Groq preferred; falls back to local automatically if unavailable.',
  },
]

const PROVIDER_INDICATOR: Record<AiMode, string> = {
  offline: 'Local',
  online: 'GroqCloud',
  hybrid: 'Hybrid (Groq + local fallback)',
}

// Left nav sections (mirrors `help-guide.tsx`'s `HelpRail` idiom below).
const SECTIONS: { id: SectionId; label: string; icon: typeof Book }[] = [
  { id: 'reading', label: 'Reading', icon: Book },
  { id: 'voice', label: 'Voice', icon: Mic },
  { id: 'theme', label: 'Theme', icon: Palette },
  { id: 'ai', label: 'AI & privacy', icon: Cpu },
  { id: 'delight', label: 'Delight', icon: Sparkles },
]

/** The left section rail — same idiom as `help-guide.tsx`'s `HelpRail`: a real vertical
 * list of `<button>`s (not a `Tabs`/`TabsList`). The active state itself (`aria-current`,
 * the `bg-accent`/`font-medium` styling) always applies instantly; only the
 * `transition-colors` decoration on top of it is gated on `useDelight().motionOk`. */
function SettingsRail({ activeId, onSelect }: { activeId: SectionId; onSelect: (id: SectionId) => void }) {
  const { motionOk } = useDelight()

  return (
    <nav
      aria-label="Settings sections"
      className="flex w-44 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-border p-2"
    >
      {SECTIONS.map(({ id, label, icon: Icon }) => {
        const isActive = id === activeId
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            aria-current={isActive ? 'true' : undefined}
            className={cn(
              'flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm',
              'focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
              isActive
                ? 'bg-accent font-medium text-accent-foreground'
                : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
              motionOk && 'transition-colors',
            )}
          >
            <Icon className="size-4 shrink-0" />
            <span className="truncate">{label}</span>
          </button>
        )
      })}
    </nav>
  )
}

/** Settings screen (docs/10 §7): Reading Comfort controls + theme/delight, all applying live.
 *
 * Two-pane layout mirroring `help-guide.tsx`: a left `SettingsRail` and a right scrolling
 * pane showing only the active section. This is a full route (not a Dialog), so the
 * two-pane row needs a DEFINITE height (`h-[calc(100vh-9rem)] min-h-0`, tuned for the
 * page header above it + `app-shell.tsx`'s `p-6` main padding) for the same reason Help's
 * `ScrollArea` needs one — without it the row grows to content height instead of scrolling. */
export function SettingsScreen() {
  const { data: values, refetch: refetchSettings } = useSettings()
  const updateSettings = useUpdateSettings()
  const openWizard = useOnboardingWizardStore((s) => s.open)

  const [activeSection, setActiveSection] = useState<SectionId>('reading')

  const [reading, setReading] = useState<ReadingControlsValue>(READING_DEFAULTS)

  // AI section local state (docs/08). The key itself is only ever held here transiently
  // (cleared right after a successful Save) — it is never written to localStorage/SQLite,
  // and `groqKeyPresent` below is the only signal we read back about it.
  const [groqModelDraft, setGroqModelDraft] = useState('')
  const [groqKeyDraft, setGroqKeyDraft] = useState('')
  const [groqKeyVisible, setGroqKeyVisible] = useState(false)
  const [groqKeyBusy, setGroqKeyBusy] = useState(false)
  const [testBusy, setTestBusy] = useState(false)
  const [disclosurePendingMode, setDisclosurePendingMode] = useState<AiMode | null>(null)

  // Voice section (docs/12): local-only read-aloud voices, per the hard rule enforced in
  // lib/speech.ts — never fetched from any other API, never falls back to a remote voice.
  const [localVoices, setLocalVoices] = useState<SpeechSynthesisVoice[]>([])
  const [voicesLoaded, setVoicesLoaded] = useState(false)
  const [ttsRateDraft, setTtsRateDraft] = useState(1.0)

  useEffect(() => {
    let cancelled = false
    void getLocalVoices().then((voices) => {
      if (cancelled) return
      setLocalVoices(voices)
      setVoicesLoaded(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

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

  // Re-seed the model-name draft the same way (never the key — that field always starts blank).
  useEffect(() => {
    if (!values) return
    setGroqModelDraft(typeof values.groq_model_name === 'string' ? values.groq_model_name : '')
  }, [values])

  useEffect(() => {
    if (!values) return
    setTtsRateDraft(typeof values.tts_rate === 'number' ? values.tts_rate : 1.0)
  }, [values])

  const themeMode: ThemeMode =
    values?.theme_mode === 'day' ||
    values?.theme_mode === 'night' ||
    values?.theme_mode === 'sunset' ||
    values?.theme_mode === 'sunrise' ||
    values?.theme_mode === 'auto'
      ? values.theme_mode
      : 'night'
  const delightLevel: DelightLevel =
    values?.delight_level === 'calm' || values?.delight_level === 'standard' ? values.delight_level : 'playful'
  const bgTint: BgTint =
    values?.bg_tint === 'cream' ||
    values?.bg_tint === 'sand' ||
    values?.bg_tint === 'peach' ||
    values?.bg_tint === 'apricot'
      ? values.bg_tint
      : 'cream'

  const aiMode: AiMode =
    values?.ai_mode === 'online' || values?.ai_mode === 'hybrid' ? values.ai_mode : 'offline'
  const groqZdrEnabled = values?.groq_zdr_enabled !== false
  const groqKeyPresent = values?.groq_key_present === true
  // Tracked as a plain setting (not localStorage) so the one-time disclosure survives a
  // reinstall the same way every other preference does — see docs/08 "Privacy & consent".
  const cloudDisclosureAck = values?.cloud_disclosure_ack === true
  // GroqCloud is only genuinely "in the loop" once a non-offline mode is selected AND a key
  // is actually on file — matches the same gate the Groq sub-panel below is shown under.
  const groqCloudOn = aiMode !== 'offline' && groqKeyPresent

  const ttsVoice = typeof values?.tts_voice === 'string' ? values.tts_voice : null

  function handleAiModeChange(next: AiMode) {
    if (next !== 'offline' && !cloudDisclosureAck) {
      setDisclosurePendingMode(next)
      return
    }
    updateSettings.mutate({ ai_mode: next })
  }

  function confirmCloudDisclosure() {
    if (disclosurePendingMode) {
      updateSettings.mutate({ ai_mode: disclosurePendingMode, cloud_disclosure_ack: true })
    }
    setDisclosurePendingMode(null)
  }

  function cancelCloudDisclosure() {
    setDisclosurePendingMode(null)
  }

  async function handleSaveGroqKey() {
    const key = groqKeyDraft.trim()
    if (!key) return
    setGroqKeyBusy(true)
    try {
      await keyring.setGroqKey(key)
      toast.success('Groq API key saved')
    } catch {
      toast.error('Could not save the Groq API key')
    } finally {
      // Clear the draft (and hide it) whether the save succeeded or failed — it never
      // lingers in component state, and it is never rendered back after saving.
      setGroqKeyDraft('')
      setGroqKeyVisible(false)
      setGroqKeyBusy(false)
      void refetchSettings()
    }
  }

  async function handleClearGroqKey() {
    setGroqKeyBusy(true)
    try {
      await keyring.clearGroqKey()
      toast.success('Groq API key cleared')
    } catch {
      toast.error('Could not clear the Groq API key')
    } finally {
      setGroqKeyBusy(false)
      void refetchSettings()
    }
  }

  async function handleTestConnection() {
    setTestBusy(true)
    try {
      const result = await keyring.testConnection()
      if (result.ok) {
        toast.success(result.provider ? `Connected via ${result.provider}` : 'Connection ok')
      } else {
        toast.error(result.reason ?? 'Connection failed')
      }
    } catch {
      toast.error('Could not test the connection')
    } finally {
      setTestBusy(false)
    }
  }

  function commitGroqModel() {
    const next = groqModelDraft.trim()
    if (next !== (typeof values?.groq_model_name === 'string' ? values.groq_model_name : '')) {
      updateSettings.mutate({ groq_model_name: next.length > 0 ? next : null })
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Every change here applies live.</p>
      </div>

      <div className="flex h-[calc(100vh-9rem)] min-h-0 overflow-hidden rounded-2xl border border-border/60">
        <SettingsRail activeId={activeSection} onSelect={setActiveSection} />
        <ScrollArea className="h-full flex-1">
          <div className="flex flex-col gap-4 p-4">
            {activeSection === 'reading' && (
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

                <div className="space-y-1.5">
                  <Label>Background tint</Label>
                  <div className="flex flex-wrap gap-2">
                    {BG_TINT_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        aria-label={opt.label}
                        aria-pressed={bgTint === opt.value}
                        title={opt.label}
                        onClick={() => updateSettings.mutate({ bg_tint: opt.value })}
                        className={cn(
                          'size-8 rounded-full border border-border transition-shadow',
                          bgTint === opt.value && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
                        )}
                        style={{ backgroundColor: BG_TINTS[opt.value].day }}
                      />
                    ))}
                  </div>
                </div>
              </section>
            )}

            {activeSection === 'voice' && (
              <section className="glass glass-edge space-y-4 rounded-2xl p-5">
                <div>
                  <h2 className="text-base font-medium">Voice</h2>
                  <p className="text-sm text-muted-foreground">
                    Read-aloud voice and speaking rate (docs/12). Only voices that run entirely on
                    this device are ever offered — manuscript text is never sent anywhere to be
                    spoken.
                  </p>
                </div>

                {voicesLoaded && localVoices.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No local voices installed on this device — read-aloud will be disabled.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    <Label htmlFor="settings-tts-voice">Voice</Label>
                    <Select
                      value={ttsVoice ?? undefined}
                      onValueChange={(next) => updateSettings.mutate({ tts_voice: next })}
                      disabled={!voicesLoaded}
                    >
                      <SelectTrigger id="settings-tts-voice" className="w-full">
                        <SelectValue placeholder={voicesLoaded ? 'Choose a voice' : 'Loading voices…'} />
                      </SelectTrigger>
                      <SelectContent>
                        {localVoices.map((voice) => (
                          <SelectItem key={voice.voiceURI} value={voice.voiceURI}>
                            {voice.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="settings-tts-rate">Speaking rate</Label>
                    <span className="text-sm text-muted-foreground tabular-nums">{ttsRateDraft.toFixed(1)}x</span>
                  </div>
                  <Slider
                    id="settings-tts-rate"
                    value={[ttsRateDraft]}
                    min={0.5}
                    max={2}
                    step={0.1}
                    onValueChange={([next]) => setTtsRateDraft(next)}
                    onValueCommit={([next]) => updateSettings.mutate({ tts_rate: next })}
                  />
                </div>
              </section>
            )}

            {activeSection === 'theme' && (
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
            )}

            {activeSection === 'ai' && (
              <section className="glass glass-edge space-y-4 rounded-2xl p-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-medium">AI &amp; privacy</h2>
                    <p className="text-sm text-muted-foreground">
                      Where Enhance, continuity, and dictation run (docs/08-AI-PROVIDER-MODES.md).
                    </p>
                  </div>
                  <Badge variant="outline">{PROVIDER_INDICATOR[aiMode]}</Badge>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  {/* Local model — the default for every AI action, zero network calls. */}
                  <div className="space-y-2 rounded-xl border-2 border-primary bg-primary/5 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Monitor className="size-4 text-primary" />
                        Local model
                      </div>
                      <Badge variant="secondary">On</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Runs on your device. Zero network calls, ever. The default for every AI
                      action.
                    </p>
                    <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                      <li>Enhance, titles, continuity</li>
                      <li>Search &amp; suggestions</li>
                    </ul>
                  </div>

                  {/* GroqCloud — opt-in, double-gated by ai_mode + the disclosure dialog below. */}
                  <div className="space-y-3 rounded-xl border border-border p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Cloud className="size-4" />
                        GroqCloud
                      </div>
                      <Badge variant={groqCloudOn ? 'secondary' : 'outline'}>
                        {groqCloudOn ? 'On' : 'Off'}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Opt-in. Uses your own free key. Sends only the text you choose to enhance —
                      retention depends on your Groq account's Zero Data Retention setting.
                    </p>

                    {aiMode !== 'offline' && (
                      <div className="space-y-4 border-t border-border pt-3">
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between">
                            <Label htmlFor="settings-groq-key">Groq API key</Label>
                            <Badge variant={groqKeyPresent ? 'secondary' : 'outline'}>
                              {groqKeyPresent ? 'Key set' : 'No key'}
                            </Badge>
                          </div>
                          <div className="flex gap-2">
                            <div className="relative flex-1">
                              <Input
                                id="settings-groq-key"
                                type={groqKeyVisible ? 'text' : 'password'}
                                value={groqKeyDraft}
                                onChange={(e) => setGroqKeyDraft(e.target.value)}
                                placeholder={groqKeyPresent ? 'Enter a new key to replace it' : 'gsk_…'}
                                autoComplete="off"
                                className="pr-9"
                              />
                              <button
                                type="button"
                                onClick={() => setGroqKeyVisible((v) => !v)}
                                className="absolute inset-y-0 right-2 flex items-center text-muted-foreground hover:text-foreground"
                                aria-label={groqKeyVisible ? 'Hide key' : 'Show key'}
                              >
                                {groqKeyVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                              </button>
                            </div>
                            <Button
                              size="sm"
                              onClick={handleSaveGroqKey}
                              disabled={groqKeyBusy || groqKeyDraft.trim().length === 0}
                            >
                              Save
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={handleClearGroqKey}
                              disabled={groqKeyBusy || !groqKeyPresent}
                            >
                              Clear
                            </Button>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Your own free key from console.groq.com. Never stored on this screen,
                            in localStorage, or in the database — see docs/08 "Secure API key
                            storage".
                          </p>
                        </div>

                        <div className="flex items-center justify-between gap-3">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleTestConnection}
                            disabled={testBusy || !groqKeyPresent}
                          >
                            Test connection
                          </Button>
                          <div className="flex items-center gap-2">
                            <Label htmlFor="settings-groq-zdr" className="text-sm">
                              Zero Data Retention
                            </Label>
                            <Switch
                              id="settings-groq-zdr"
                              checked={groqZdrEnabled}
                              onCheckedChange={(checked) => updateSettings.mutate({ groq_zdr_enabled: checked })}
                            />
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <Label htmlFor="settings-groq-model">Groq model (heavy-lift tasks)</Label>
                          <Input
                            id="settings-groq-model"
                            value={groqModelDraft}
                            onChange={(e) => setGroqModelDraft(e.target.value)}
                            onBlur={commitGroqModel}
                            placeholder="openai/gpt-oss-120b"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <RadioGroup
                  value={aiMode}
                  onValueChange={(v: AiMode) => handleAiModeChange(v)}
                  className="flex flex-col gap-2"
                >
                  {AI_MODE_OPTIONS.map((opt) => {
                    const id = `settings-ai-mode-${opt.value}`
                    return (
                      <label
                        key={opt.value}
                        htmlFor={id}
                        className={cn(
                          'flex cursor-pointer items-start gap-2 rounded-xl border border-border px-3 py-2 transition-colors hover:bg-accent/50',
                          aiMode === opt.value && 'border-primary bg-primary/5 ring-1 ring-primary/30',
                        )}
                      >
                        <RadioGroupItem value={opt.value} id={id} className="mt-0.5" />
                        <div>
                          <Label htmlFor={id} className="text-sm">
                            {opt.label}
                          </Label>
                          <p className="text-xs text-muted-foreground">{opt.description}</p>
                        </div>
                      </label>
                    )
                  })}
                </RadioGroup>

                <div className="flex items-start gap-2 rounded-xl border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <p>
                    Zero-data-retention is an account-level Groq setting — enabling it here won't
                    enforce it per request. Turn on ZDR in your Groq console too.
                  </p>
                </div>
              </section>
            )}

            {activeSection === 'delight' && (
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
            )}
          </div>
        </ScrollArea>
      </div>

      <Dialog open={disclosurePendingMode !== null} onOpenChange={(open) => !open && cancelCloudDisclosure()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sending text to GroqCloud</DialogTitle>
            <DialogDescription>
              Online and Hybrid mode send the text you choose to enhance to GroqCloud, a
              third-party service, for that request only. Groq states it doesn't train on
              this data; Zero Data Retention is available as an account-level setting in your
              Groq console. If you're working on something you don't want leaving this machine,
              stay in Offline mode.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={cancelCloudDisclosure}>
              Cancel
            </Button>
            <Button onClick={confirmCloudDisclosure}>Confirm</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

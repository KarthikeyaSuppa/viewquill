import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { Loader2, Mic, Square } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { useSettings } from '@/queries/settings'
import { useTranscribe } from '@/queries/voice'

const DEFAULT_HOTKEY = 'CmdOrCtrl+Shift+Space'

/** A parsed `dictation_hotkey` setting value (e.g. `"CmdOrCtrl+Shift+Space"`, docs/03
 * `app_settings`). `cmdOrCtrl` is its own flag (matches either Ctrl or Meta being held) —
 * cross-platform accelerator strings like Electron/Tauri's use it distinctly from a
 * literal `Ctrl` or `Cmd` token. */
interface ParsedHotkey {
  cmdOrCtrl: boolean
  ctrl: boolean
  meta: boolean
  shift: boolean
  alt: boolean
  key: string
}

function parseHotkey(spec: string): ParsedHotkey {
  const parsed: ParsedHotkey = { cmdOrCtrl: false, ctrl: false, meta: false, shift: false, alt: false, key: '' }
  for (const raw of spec.split('+')) {
    const token = raw.trim().toLowerCase()
    if (!token) continue
    if (token === 'cmdorctrl') parsed.cmdOrCtrl = true
    else if (token === 'ctrl' || token === 'control') parsed.ctrl = true
    else if (token === 'cmd' || token === 'meta' || token === 'command') parsed.meta = true
    else if (token === 'shift') parsed.shift = true
    else if (token === 'alt' || token === 'option') parsed.alt = true
    else parsed.key = token
  }
  return parsed
}

function keyMatches(event: KeyboardEvent, key: string): boolean {
  if (!key) return false
  if (key === 'space') return event.code === 'Space'
  return event.key.toLowerCase() === key || event.code.toLowerCase() === `key${key}`
}

function hotkeyMatches(event: KeyboardEvent, hotkey: ParsedHotkey): boolean {
  if (!keyMatches(event, hotkey.key)) return false
  if (hotkey.shift !== event.shiftKey) return false
  if (hotkey.alt !== event.altKey) return false
  if (hotkey.cmdOrCtrl) return event.ctrlKey || event.metaKey
  return hotkey.ctrl === event.ctrlKey && hotkey.meta === event.metaKey
}

/** Best-effort caret insertion for a dictated transcript into a controlled field's value.
 * Falls back to a plain append if the field isn't focused / doesn't support selection
 * ranges (e.g. its ref went stale). Callers own writing the returned string into their own
 * state — this never mutates anything itself. */
export function insertAtCaret(
  el: HTMLInputElement | HTMLTextAreaElement | null,
  currentValue: string,
  transcript: string,
): string {
  if (!transcript) return currentValue
  if (!el || document.activeElement !== el || el.selectionStart === null) {
    if (currentValue.length === 0) return transcript
    return currentValue.endsWith(' ') ? `${currentValue}${transcript}` : `${currentValue} ${transcript}`
  }
  const start = el.selectionStart
  const end = el.selectionEnd ?? start
  const next = currentValue.slice(0, start) + transcript + currentValue.slice(end)
  const caretPos = start + transcript.length
  // Restore the caret just past the inserted text once React commits the new controlled
  // value — a microtask is enough to run right after this render.
  queueMicrotask(() => {
    try {
      el.setSelectionRange(caretPos, caretPos)
    } catch {
      /* some input types don't support selection ranges — safe to ignore */
    }
  })
  return next
}

export interface MicButtonProps {
  /** Called once with the transcript after a recording finishes and transcribes. Never
   * called with an empty string. */
  onTranscript: (text: string) => void
  /** The field this mic is paired with. When provided, the global push-to-talk hotkey
   * (`dictation_hotkey` setting) only triggers THIS mic while that field is focused — lets
   * several MicButtons coexist (Title, Description, each screenplay element) without
   * fighting over the same hotkey. Omit for a click-only mic. */
  fieldRef?: RefObject<HTMLElement | null>
  /** Accessible label for this mic's field, e.g. "Title". */
  label?: string
  className?: string
}

/**
 * Press-and-hold dictation mic (docs/12-VOICE-AND-SPEECH.md §1, docs/06 Phase 2 task H4).
 * Records via the browser's `MediaRecorder` while held (pointer or the paired field's
 * push-to-talk hotkey), then POSTs the blob to `/voice/transcribe` via `useTranscribe()`.
 *
 * Trust rule: recording must be visibly obvious — the button turns solid red and pulses
 * for the entire time the mic is live, never silently.
 *
 * [MODEL-DEFERRED]: the sidecar's STT stub returns fixed text on this build machine; real
 * transcription quality is only exercised on the second ("AI") laptop. This component only
 * needs to wire the audio path correctly, not judge transcript quality.
 */
export function MicButton({ onTranscript, fieldRef, label = 'Dictate', className }: MicButtonProps) {
  const { data: settings } = useSettings()
  const transcribe = useTranscribe()
  const [isRecording, setIsRecording] = useState(false)
  const isRecordingRef = useRef(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const streamRef = useRef<MediaStream | null>(null)

  const hotkeySpec = typeof settings?.dictation_hotkey === 'string' ? settings.dictation_hotkey : DEFAULT_HOTKEY

  const stopRecording = useCallback(() => {
    if (!isRecordingRef.current) return
    isRecordingRef.current = false
    setIsRecording(false)
    mediaRecorderRef.current?.stop()
  }, [])

  const startRecording = useCallback(async () => {
    if (isRecordingRef.current) return
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      toast.error('Microphone not available in this environment')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        streamRef.current = null
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        chunksRef.current = []
        transcribe.mutate(blob, {
          onSuccess: (note) => {
            if (note.transcript) onTranscript(note.transcript)
          },
        })
      }
      recorder.start()
      isRecordingRef.current = true
      setIsRecording(true)
    } catch {
      toast.error('Microphone permission denied — check your browser/OS settings')
    }
  }, [onTranscript, transcribe])

  // Push-to-talk global hotkey — only acts while THIS mic's paired field is focused.
  useEffect(() => {
    if (!fieldRef) return
    const ref = fieldRef
    const hotkey = parseHotkey(hotkeySpec)

    function handleKeyDown(event: KeyboardEvent) {
      if (event.repeat) return
      if (document.activeElement !== ref.current) return
      if (!hotkeyMatches(event, hotkey)) return
      event.preventDefault()
      void startRecording()
    }
    function handleKeyUp(event: KeyboardEvent) {
      if (!isRecordingRef.current) return
      if (!hotkeyMatches(event, hotkey)) return
      event.preventDefault()
      stopRecording()
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
    }
  }, [fieldRef, hotkeySpec, startRecording, stopRecording])

  // If this button unmounts mid-recording (e.g. the drawer closes), release the mic stream
  // rather than leaving it live in the background.
  useEffect(() => {
    return () => {
      mediaRecorderRef.current?.stop()
      streamRef.current?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  const transcribing = transcribe.isPending

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={isRecording ? 'destructive' : 'ghost'}
          size="icon-sm"
          disabled={transcribing}
          aria-label={isRecording ? `Recording ${label} — release to stop` : `Dictate ${label} (hold to record)`}
          aria-pressed={isRecording}
          className={cn(isRecording && 'animate-pulse', className)}
          onPointerDown={(event) => {
            event.preventDefault()
            void startRecording()
          }}
          onPointerUp={stopRecording}
          onPointerLeave={() => {
            if (isRecordingRef.current) stopRecording()
          }}
          onPointerCancel={stopRecording}
        >
          {transcribing ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : isRecording ? (
            <Square className="size-3.5" />
          ) : (
            <Mic className="size-3.5" />
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {transcribing ? 'Transcribing…' : isRecording ? 'Recording — release to stop' : `Hold to dictate ${label}`}
      </TooltipContent>
    </Tooltip>
  )
}

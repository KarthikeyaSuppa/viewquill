import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { API_BASE, ApiError, type VoiceNote } from '@/lib/api'

/**
 * POSTs a raw recorded audio `Blob` straight to the sidecar's `/voice/transcribe`
 * (docs/12-VOICE-AND-SPEECH.md §1, docs/06 Phase 2 task H4). Unlike the rest of
 * `lib/api.ts`, this is NOT JSON — the body is the audio bytes themselves with a
 * `Content-Type` matching the blob (falling back to `audio/webm`), per `app/api/voice.py`'s
 * "raw request body, not multipart" contract.
 *
 * [SECURITY-REVIEW] rides on this path per CLAUDE.md — raw user audio leaves the browser
 * here. See `app/api/voice.py` + `app/services/speech_stt.py` for the sidecar side, which
 * is where that review belongs, not this hook.
 *
 * [MODEL-DEFERRED]: on this build machine the sidecar's STT stub returns fixed text —
 * real transcription quality only gets exercised on the second ("AI") laptop.
 */
export function useTranscribe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (blob: Blob) => {
      const res = await fetch(`${API_BASE}/voice/transcribe`, {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'audio/webm' },
        body: blob,
      })
      if (!res.ok) {
        throw new ApiError(`POST /voice/transcribe → ${res.status}`, res.status)
      }
      return (await res.json()) as VoiceNote
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['voice-notes'] })
    },
    onError: () => toast.error('Could not transcribe the recording'),
  })
}

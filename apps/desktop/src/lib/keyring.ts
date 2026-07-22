/**
 * DEV SEAM — currently calls the sidecar's in-memory key endpoints; in the packaged app
 * this will `invoke()` a Tauri command that reads/writes the OS keyring (docs/08). The key
 * is never stored in localStorage or SQLite.
 *
 * See apps/sidecar/app/api/llm.py ("The Groq key seam") and
 * apps/sidecar/app/services/groq_key.py for the backend half of this seam: the raw key
 * lives only in a process-lifetime module variable there, never persisted, and is never
 * echoed back by any response — only a computed `groq_key_present` boolean is exposed via
 * `/settings`.
 */

import { api } from '@/lib/api'
import type { GroqKeyPresence, TestConnectionResult } from '@/lib/api'

/** Sets/replaces the Groq API key. Resolves to `{ present: true }`; never returns the key. */
export function setGroqKey(key: string): Promise<GroqKeyPresence> {
  return api.post<GroqKeyPresence>('/llm/groq-key', { key })
}

/** Clears the stored key (204 No Content). */
export function clearGroqKey(): Promise<void> {
  return api.delete('/llm/groq-key')
}

/** Fires one minimal Groq call against the currently-set key + configured model. */
export function testConnection(): Promise<TestConnectionResult> {
  return api.post<TestConnectionResult>('/llm/test-connection')
}

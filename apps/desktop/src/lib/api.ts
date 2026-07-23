import { useAuthStore } from '@/stores/auth'

/**
 * Typed client for the Python sidecar (docs/02). In dev the sidecar is a fixed localhost
 * port; under Tauri the Rust shell will hand us the dynamic port via `get_backend_port()`
 * — swap `resolveBaseUrl` then, nothing else changes.
 */

const DEV_SIDECAR_URL = 'http://127.0.0.1:8756'

function resolveBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_SIDECAR_URL as string | undefined
  return fromEnv ?? DEV_SIDECAR_URL
}

export const API_BASE = resolveBaseUrl()

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Read the store outside React (no hook context here) so every call — including ones
  // made before any component renders — picks up the current session token, if any.
  const token = useAuthStore.getState().token
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!res.ok) {
    throw new ApiError(`${init?.method ?? 'GET'} ${path} → ${res.status}`, res.status)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, init),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  delete: <T = void>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// ── Local profiles & auth (mirrors app/models/schemas.py Profile*/Login*; UI/profile
// LOCK only — the password gates who's at the keyboard, it never encrypts data). ──
export interface Profile {
  id: string
  username: string
  display_name: string | null
  avatar: string
}

export interface LoginResponse {
  token: string
  user: Profile
}

// ── Contracts (mirror app/models/schemas.py; superseded later by generated api-types) ──
export interface OllamaHealth {
  reachable: boolean
  base_url: string
  detail: string | null
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  service: string
  version: string
  database: 'ok' | 'error'
  ollama: OllamaHealth
}

export interface SettingsResponse {
  values: Record<string, unknown>
}

// ── AI provider modes / Groq key seam (mirrors app/models/schemas.py GroqKey*/TestConnectionResult;
// docs/08-AI-PROVIDER-MODES.md, docs/06 Phase 2 tasks F2/F3). The key itself never appears here —
// only presence/success booleans. See src/lib/keyring.ts for the DEV-SEAM-ONLY note. ──
export interface GroqKeyPresence {
  present: boolean
}

export interface TestConnectionResult {
  ok: boolean
  reason: string | null
  provider: string | null
}

// ── Node Canvas (mirrors app/models/schemas.py Scene/CanvasNode/CanvasEdge; docs/06 Phase 2) ──
export type NodeType = 'scene' | 'plot_point' | 'thought'
export type ConnectionType = 'sequence' | 'causal' | 'reference' | 'contradiction' | 'custom'

/** The canonical Scene row — shared across Books, not per-canvas. */
export interface Scene {
  id: string
  node_type: NodeType
  title: string
  description: string | null
  status: string | null
  word_count: number
  created_at: string
  updated_at: string
}

/** A Scene as placed on one Book's canvas (canonical Scene fields + this Book's link). */
export interface CanvasNode {
  link_id: string
  scene_id: string
  node_type: NodeType
  title: string
  description: string | null
  status: string | null
  canvas_x: number | null
  canvas_y: number | null
  color: string | null
}

export interface CanvasEdge {
  id: string
  source_scene_id: string
  target_scene_id: string
  source_handle: string | null
  target_handle: string | null
  connection_type: ConnectionType | null
  label: string | null
}

export interface CanvasResponse {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

// ── Codex (mirrors app/models/schemas.py CodexEntry*; docs/06 Phase 2 tasks B1/B2, H3).
// Full custom-fields/relationships/arc editor is Phase 3 (docs/06) — this is the MVP shape. ──
export type CodexEntryType = 'character' | 'location' | 'faction' | 'object_lore'

/** A Codex entry — canonical and shared across Books, like Scene. */
export interface CodexEntry {
  id: string
  entry_type: CodexEntryType
  name: string
  summary: string | null
  custom_fields: Record<string, unknown> | null
  primary_image_id: string | null
  created_at: string
  updated_at: string
}

// ── Voice notes (mirrors app/models/schemas.py VoiceNote*; docs/12, docs/06 Phase 2 H4).
// [SECURITY-REVIEW] rides on the audio path — see app/api/voice.py + app/services/speech_stt.py. ──
export type VoiceNoteStatus = 'recorded' | 'transcribed' | 'attached' | 'discarded'

export interface VoiceNote {
  id: string
  audio_path: string
  transcript: string | null
  engine: string | null
  duration_ms: number | null
  attached_entity_type: string | null
  attached_entity_id: string | null
  status: VoiceNoteStatus
  created_at: string
}

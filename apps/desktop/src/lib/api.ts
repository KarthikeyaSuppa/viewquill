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
  /** The server's `{ detail: "..." }` message, when the error body was JSON with one —
   * lets callers (e.g. Phase 7's bundle export/import flows) surface the real reason
   * (wrong passphrase, corrupt file, unsupported version) instead of a generic message. */
  readonly detail: string | null
  constructor(message: string, status: number, detail: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** Best-effort extraction of FastAPI's `{ detail: string }` error body. Never throws —
 * a non-JSON or bodyless error response just yields `null`, and the caller falls back to
 * its generic message. Uses `res.clone()` so the original body is still readable by the
 * caller if it wants the raw response for anything else. */
async function extractErrorDetail(res: Response): Promise<string | null> {
  try {
    const body = await res.clone().json()
    if (body && typeof body.detail === 'string') return body.detail
  } catch {
    // not JSON / empty body — fine, caller falls back to a generic message
  }
  return null
}

function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null
  const match = /filename="?([^"]+)"?/.exec(header)
  return match ? match[1] : null
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
    const detail = await extractErrorDetail(res)
    throw new ApiError(`${init?.method ?? 'GET'} ${path} → ${res.status}`, res.status, detail)
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
  /** POSTs JSON, expects a raw binary response (`application/octet-stream`) rather than
   * JSON — for Phase 7's encrypted `.quillproj` export, which streams back the bundle
   * bytes directly instead of a JSON body. Returns the blob plus the filename the server
   * chose via `Content-Disposition`, if present. */
  postBlob: async (
    path: string,
    body: unknown,
  ): Promise<{ blob: Blob; filename: string | null }> => {
    const token = useAuthStore.getState().token
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const detail = await extractErrorDetail(res)
      throw new ApiError(`POST ${path} → ${res.status}`, res.status, detail)
    }
    const blob = await res.blob()
    const filename = filenameFromContentDisposition(res.headers.get('Content-Disposition'))
    return { blob, filename }
  },
  /** POSTs a raw binary body (not JSON, not multipart) with extra headers/query params —
   * for Phase 7's `.quillproj` import inspect/apply endpoints, which take the encrypted
   * bundle bytes as the literal request body and the passphrase via a custom header. */
  postRaw: async <T>(
    path: string,
    body: ArrayBuffer,
    extraHeaders: Record<string, string> = {},
    query?: Record<string, string>,
  ): Promise<T> => {
    const token = useAuthStore.getState().token
    const qs = query ? `?${new URLSearchParams(query).toString()}` : ''
    const res = await fetch(`${API_BASE}${path}${qs}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...extraHeaders,
      },
      body,
    })
    if (!res.ok) {
      const detail = await extractErrorDetail(res)
      throw new ApiError(`POST ${path} → ${res.status}`, res.status, detail)
    }
    return (await res.json()) as T
  },
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
  /** Nullable rendering/sort hint marking this edge as part of the lineage/sequence view
   * (vs. an arbitrary free-form connection); NULL is the default and means "not lineage".
   * Nothing writes this yet — it's rendered read-only per `InkEdge`. */
  sequence_weight: number | null
}

export interface CanvasResponse {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

/** Mirrors app/models/schemas.py UndoActionRead — the row popped/re-applied by
 * `POST /books/{book_id}/undo` and `/redo` (PHASE11.md Workstream B task 7/10). Scoped to the
 * single most-recent undoable action for the Book, not a deep history stack. */
export interface UndoAction {
  id: string
  action_type: string
  scene_id: string | null
  undone_at: string | null
  created_at: string
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

// ── Codex relationships & arc states (mirrors app/models/schemas.py CodexRelationship*/
// CodexArcState*; docs/06 Phase 3 Codex tasks). ──
export interface CodexRelationship {
  id: string
  from_entry_id: string
  to_entry_id: string
  relationship_type: string
  description: string | null
}

export interface CodexArcState {
  id: string
  codex_entry_id: string
  book_id: string
  as_of_outline_order_index: number
  status_summary: string | null
  traits_snapshot: Record<string, unknown> | null
  created_at: string
}

// ── Images (mirrors app/models/schemas.py ImageRead/EntityImageRead; docs/06 Phase 3 BE-3,
// Phase 5 BE-1..BE-4). Upload is a raw request body (not multipart, not JSON) — see
// useUploadImage in src/queries/codex.ts (Phase 3, Codex-entry-scoped) and the fuller
// src/queries/images.ts (Phase 5, the Images tab + reference-pool gallery). ──
export type ImageBucket = 'reference_pool' | 'finalized_scene'

export interface ImageRead {
  id: string
  bucket: ImageBucket
  storage_path: string
  display_name: string
  original_filename: string | null
  description: string | null
  width: number | null
  height: number | null
  checksum_sha256: string | null
  tags: string[]
  created_at: string
  updated_at: string
}

// ── Entity <-> Image links (mirrors app/models/schemas.py EntityImageRead/
// EntityImageLinkCreate; docs/06 Phase 5 task BE-3) — a many-to-many attach list (e.g. a
// Scene's moodboard), independent of single-slot pointers like `primary_image_id`. ──
export type EntityImageEntityType = 'book' | 'scene' | 'codex_entry'

export interface EntityImageRead {
  id: string
  image_id: string
  entity_type: EntityImageEntityType
  entity_id: string
  role: string | null
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

// ── Structure templates & Chapters (mirrors app/models/schemas.py StructureTemplate*/
// Chapter*; docs/06 Phase 4 Outline/Timeline). ──
export interface StructureTemplateBeat {
  name: string
  order_index: number
  description: string
}

export interface StructureTemplate {
  id: string
  name: string
  applicable_book_types: string[] | null
  beats: StructureTemplateBeat[] | null
}

export interface Chapter {
  id: string
  book_id: string
  title: string
  order_index: number
}

// ── Outline/Timeline (mirrors app/models/schemas.py BookSceneOrder*; docs/06 Phase 4).
// One row type backs both the Outline view and the Timeline view. ──
export interface BookSceneOrder {
  id: string
  book_id: string
  scene_id: string
  chapter_id: string | null
  outline_order_index: number | null
  structure_beat: string | null
  timeline_order_index: number | null
  in_story_time_label: string | null
  in_story_time_sort_key: number | null
}

// ── Continuity (mirrors app/models/schemas.py ContinuityFlagRead; docs/06 Phase 4).
// `source` is nullable at the DB/schema level even though the check constraint restricts
// non-null values to the three below. ──
export type ContinuitySeverity = 'critical' | 'warning' | 'hint'
export type ContinuityStatus = 'open' | 'dismissed' | 'resolved'
export type ContinuitySource = 'deterministic' | 'ai' | 'manual'

export interface ContinuityFlag {
  id: string
  book_id: string
  scene_id: string | null
  codex_entry_id: string | null
  flag_type: string | null
  severity: ContinuitySeverity
  description: string
  status: ContinuityStatus
  source: ContinuitySource | null
  created_at: string
}

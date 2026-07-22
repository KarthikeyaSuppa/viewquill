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
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    throw new ApiError(`${init?.method ?? 'GET'} ${path} → ${res.status}`, res.status)
  }
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, init),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
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

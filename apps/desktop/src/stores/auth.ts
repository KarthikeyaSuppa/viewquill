import { create } from 'zustand'
import type { Profile } from '@/lib/api'

/**
 * Local-profile session (docs/0X auth). This is a UI/profile lock, not encryption —
 * the password gates who's "at the keyboard" locally; it never encrypts data.
 *
 * Deliberately **memory-only** — never persisted to localStorage/sessionStorage — so
 * relaunching the app always re-shows the profile picker (`ProfileGate`) rather than
 * silently resuming someone else's session.
 */
interface AuthState {
  token: string | null
  user: Profile | null
  setSession: (token: string, user: Profile) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  setSession: (token, user) => set({ token, user }),
  clear: () => set({ token: null, user: null }),
}))

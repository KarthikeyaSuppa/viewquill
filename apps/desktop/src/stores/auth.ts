import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { Profile } from '@/lib/api'

/**
 * Local-profile session (docs/0X auth). This is a UI/profile lock, not encryption —
 * the password gates who's "at the keyboard" locally; it never encrypts data.
 *
 * Persisted to **`sessionStorage`** (not `localStorage`): a page refresh/reload keeps the
 * signed-in session (so the dev server / WebView reload no longer bounces you to the
 * picker), but fully closing the app still clears it — so relaunching returns to the
 * `ProfileGate` rather than silently resuming the last profile's session on this shared
 * 2-profile machine. That preserves the original memory-only intent across a real relaunch
 * while fixing refresh. (User choice, PHASE13 follow-up — was previously memory-only.)
 *
 * Note: server-side session tokens are themselves in-memory (`sessions_service.py`), so if
 * the sidecar restarts a persisted token becomes stale; the next authed request 401s and the
 * user re-signs in. That's the expected edge, not a regression.
 */
interface AuthState {
  token: string | null
  user: Profile | null
  setSession: (token: string, user: Profile) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setSession: (token, user) => set({ token, user }),
      clear: () => set({ token: null, user: null }),
    }),
    {
      name: 'quillnight-auth',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)

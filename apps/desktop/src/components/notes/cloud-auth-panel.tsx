import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { NoteEditor } from '@/components/notes/note-editor'
import { createCloudAdapter } from '@/lib/sync/cloud-adapter'
import {
  configureFirebase,
  getFirebaseConfig,
  onAuthChange,
  signInWithGoogle,
  signOutUser,
  type User,
} from '@/lib/firebase'
import { useSettings } from '@/queries/settings'

/**
 * The Cloud pane's brain (T7+T8). Note this is one of exactly two files allowed to touch
 * `src/lib/firebase.ts` (the other is `src/lib/sync/cloud-adapter.ts`) — it never imports
 * `firebase`/`firebase/*` directly, only the wrapper surface `firebase.ts` exports.
 *
 * Three states, driven by `useSettings()` + `onAuthChange`:
 *  1. No valid `firebase_web_config` → a "connect a project" card pointing at
 *     Settings → Notes. Nothing Firebase-related runs at all in this state.
 *  2. Configured but signed out → a "Sign in with Google" button.
 *  3. Signed in → account chip + Sign out + the cloud `NoteEditor`, bound to
 *     `notes/{uid}` via `createCloudAdapter(uid)`.
 */

/** Turns the SDK's own `FirebaseError`-shaped rejection into copy a user can act on,
 * without importing anything from `firebase` — duck-typed on `.code`, which every
 * `firebase/auth` error carries. */
function describeSignInError(err: unknown): string {
  const code =
    typeof err === 'object' && err !== null && 'code' in err ? String((err as { code: unknown }).code) : null
  switch (code) {
    case 'auth/popup-blocked':
      return 'Your browser blocked the sign-in popup. Allow popups for this app and try again.'
    case 'auth/popup-closed-by-user':
    case 'auth/cancelled-popup-request':
      return 'Sign-in was closed before finishing — try again.'
    case 'auth/network-request-failed':
      return 'Could not reach Google. Check your connection and try again.'
    default:
      return 'Could not sign in with Google. Try again in a moment.'
  }
}

export function CloudAuthPanel() {
  const { data: values } = useSettings()
  const navigate = useNavigate()

  const rawConfig = typeof values?.firebase_web_config === 'string' ? values.firebase_web_config : null
  const config = useMemo(() => getFirebaseConfig(rawConfig), [rawConfig])

  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  const [signingIn, setSigningIn] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!config) {
      setUser(null)
      setReady(false)
      return
    }
    configureFirebase(config)
    setReady(true)
    const unsubscribe = onAuthChange((next) => {
      setUser(next)
      // A fresh sign-in/out attempt is over, whichever way it landed — clear any stale
      // error so it doesn't linger next to a now-successful sign-in.
      setError(null)
    })
    return unsubscribe
  }, [config])

  async function handleSignIn() {
    setError(null)
    setSigningIn(true)
    try {
      await signInWithGoogle()
    } catch (err) {
      setError(describeSignInError(err))
    } finally {
      setSigningIn(false)
    }
  }

  async function handleSignOut() {
    setError(null)
    try {
      await signOutUser()
    } catch {
      setError('Could not sign out — try again.')
    }
  }

  if (!config) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border p-8 text-center">
        <p className="text-sm font-medium">Connect a Firebase project to sync your note anywhere</p>
        <p className="max-w-xs text-xs text-muted-foreground">
          Your story stays local — only this one note ever syncs, and only once you connect an
          account.
        </p>
        <Button variant="outline" size="sm" onClick={() => navigate('/settings?section=notes')}>
          Set up in Settings → Notes
        </Button>
      </div>
    )
  }

  if (!ready || !user) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">Sign in with Google to enable your cloud note</p>
        <Button variant="outline" size="sm" onClick={handleSignIn} disabled={signingIn}>
          {signingIn ? 'Signing in…' : 'Sign in with Google'}
        </Button>
        {error && (
          <p role="alert" className="text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {user.photoURL ? (
            <img src={user.photoURL} alt="" className="size-6 shrink-0 rounded-full" referrerPolicy="no-referrer" />
          ) : null}
          <span className="truncate text-sm text-muted-foreground">
            {user.email ?? user.displayName ?? 'Signed in'}
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleSignOut}>
          <LogOut className="size-4" />
          Sign out
        </Button>
      </div>

      <NoteEditor channel="cloud" adapterFactory={() => createCloudAdapter(user.uid)} className="flex-1" />

      {error && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}

/**
 * ── THE NETWORK WALL (T7+T8) ──────────────────────────────────────────────
 * This is the ONLY file in the entire frontend allowed to `import` from
 * `firebase`/`firebase/*`. Every other file that needs auth/Firestore goes
 * through the small surface exported here (`configureFirebase`,
 * `getFirebaseAuth`, `getFirestoreDb`, `signInWithGoogle`, `signOutUser`,
 * `onAuthChange`, `getCurrentUid`, `getFirebaseConfig`, plus the re-exported
 * `User`/`FirebaseWebConfig` types). The Python sidecar makes zero cloud
 * calls (docs/02-ARCHITECTURE.md) — this module is the entire cloud surface
 * for the desktop app, and it is entirely opt-in: nothing here runs unless
 * the user has pasted a Firebase web config into Settings → Notes.
 *
 * A reviewer will grep the repo for `from 'firebase` / `from "firebase` and
 * expect exactly one hit: this file. Do not import the SDK anywhere else —
 * add a wrapper function here instead.
 */

import {
  deleteApp,
  getApp,
  getApps,
  initializeApp,
  type FirebaseApp,
} from 'firebase/app'
import {
  browserLocalPersistence,
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  setPersistence,
  signInWithPopup,
  signOut,
  type Auth,
  type User,
} from 'firebase/auth'
import {
  doc as firestoreDoc,
  initializeFirestore,
  onSnapshot as firestoreOnSnapshot,
  persistentLocalCache,
  persistentSingleTabManager,
  setDoc as firestoreSetDoc,
  type DocumentData,
  type DocumentReference,
  type DocumentSnapshot,
  type Firestore,
  type FirestoreError,
  type SnapshotListenOptions,
  type Unsubscribe,
} from 'firebase/firestore'

/** Re-exported so other modules (e.g. `cloud-auth-panel.tsx`) can type
 * against the signed-in user without importing `firebase/auth` themselves. */
export type { User }

/** The Firebase **web config** the user pastes into Settings → Notes — this
 * is the publishable client config (apiKey here is not a secret; Firestore
 * security is enforced by `firebase/firestore.rules`, not by hiding this
 * value), not a service-account credential. Mirrors the shape of the object
 * the Firebase console's "Add app" flow hands out. */
export interface FirebaseWebConfig {
  apiKey: string
  authDomain?: string
  projectId: string
  storageBucket?: string
  messagingSenderId?: string
  appId: string
  measurementId?: string
}

/** Thrown by `getFirebaseAuth()`/`getFirestoreDb()` when called before a
 * valid config has been supplied via `configureFirebase()`. Typed so callers
 * can tell "not configured yet" apart from a real network/auth failure. */
export class FirebaseNotConfiguredError extends Error {
  constructor() {
    super('Firebase is not configured — paste a web config into Settings → Notes first.')
    this.name = 'FirebaseNotConfiguredError'
  }
}

const REQUIRED_KEYS: (keyof FirebaseWebConfig)[] = ['apiKey', 'projectId', 'appId']

/**
 * Parses+validates the raw JSON string stored at the `firebase_web_config`
 * app-setting key (`useSettings()` values, docs/03). Pure/stateless — does
 * not read settings itself (callers pass the string they got from
 * `useSettings()`) and does not touch the network. Returns `null` for
 * absent/blank/unparseable/missing-required-key input rather than throwing,
 * so call sites can do `const config = getFirebaseConfig(raw)` and branch on
 * null without a try/catch.
 */
export function getFirebaseConfig(raw: string | null | undefined): FirebaseWebConfig | null {
  if (typeof raw !== 'string' || raw.trim().length === 0) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null) return null
  const candidate = parsed as Record<string, unknown>
  for (const key of REQUIRED_KEYS) {
    if (typeof candidate[key] !== 'string' || (candidate[key] as string).trim().length === 0) {
      return null
    }
  }
  return candidate as unknown as FirebaseWebConfig
}

let app: FirebaseApp | null = null
let authInstance: Auth | null = null
let dbInstance: Firestore | null = null
// Fingerprint of the config `app`/`authInstance`/`dbInstance` were built from — lets
// `configureFirebase` tell "already configured with this exact config, no-op" apart from
// "configured with a stale one, tear down and rebuild" (e.g. the user edits the pasted
// config in Settings while the app is still running).
let configuredWith: string | null = null

/**
 * Lazily initializes the Firebase app/auth/Firestore singletons from a
 * validated config. Safe to call on every render/mount (idempotent — a
 * second call with the same config is a no-op); if called with a *different*
 * config than the one currently active, the old app is torn down first
 * (`deleteApp`) so a user who edits Settings mid-session doesn't end up
 * silently talking to the wrong Firebase project.
 */
export function configureFirebase(config: FirebaseWebConfig): void {
  const fingerprint = JSON.stringify(config)
  if (configuredWith === fingerprint && app) return

  if (app) {
    // Config changed out from under an already-initialized app — rebuild clean rather
    // than leaving stale auth/Firestore instances pointed at the old project.
    void deleteApp(app).catch(() => {
      // Best-effort teardown; a failure here just means we leak the old app object,
      // which is harmless since nothing keeps a reference to it after this function
      // returns — the new `initializeApp` below still gets a correct, working app.
    })
    app = null
    authInstance = null
    dbInstance = null
  }

  app = getApps().length > 0 ? getApp() : initializeApp(config)

  dbInstance = initializeFirestore(app, {
    // Offline persistence via the modern cache API — NOT the deprecated
    // `enableIndexedDbPersistence`, which Firebase has removed guidance for in favor of
    // this settings-based form. Single-tab manager: this is a single-window desktop app
    // (Tauri), so there is no multi-tab case to coordinate.
    localCache: persistentLocalCache({ tabManager: persistentSingleTabManager(undefined) }),
  })

  authInstance = getAuth(app)
  // Fire-and-forget: session persistence across restarts. A failure here (e.g. Firestore
  // running in an environment without storage access) degrades to in-memory-only auth
  // rather than crashing configuration.
  void setPersistence(authInstance, browserLocalPersistence).catch(() => {})

  configuredWith = fingerprint
}

/** Returns the initialized `Auth` instance, or throws `FirebaseNotConfiguredError` if
 * `configureFirebase()` hasn't been called yet with a valid config. */
export function getFirebaseAuth(): Auth {
  if (!authInstance) throw new FirebaseNotConfiguredError()
  return authInstance
}

/** Returns the initialized Firestore `Firestore` instance, or throws
 * `FirebaseNotConfiguredError` if not yet configured. Used by
 * `src/lib/sync/cloud-adapter.ts` — the only other file allowed to touch this module's
 * Firebase-backed exports. */
export function getFirestoreDb(): Firestore {
  if (!dbInstance) throw new FirebaseNotConfiguredError()
  return dbInstance
}

/** Opens the Google sign-in popup. Throws `FirebaseNotConfiguredError` if not configured;
 * otherwise rejects with the SDK's own `FirebaseError` (has a `.code` like
 * `'auth/popup-blocked'`/`'auth/popup-closed-by-user'`) on failure — callers (only
 * `cloud-auth-panel.tsx`) turn that into a readable message via a duck-typed check on
 * `.code`, without needing to import anything from `firebase` themselves. */
export async function signInWithGoogle(): Promise<User> {
  const auth = getFirebaseAuth()
  const provider = new GoogleAuthProvider()
  const result = await signInWithPopup(auth, provider)
  return result.user
}

/** Signs out of the currently configured Firebase project. No-op (resolves) if not
 * configured — signing out of nothing is not an error. */
export async function signOutUser(): Promise<void> {
  if (!authInstance) return
  await signOut(authInstance)
}

/** Subscribes to auth state changes (`null` = signed out). Returns an unsubscribe
 * function. If Firebase isn't configured yet, fires `cb(null)` once and returns a no-op
 * unsubscribe — callers don't need to special-case "not configured" themselves. */
export function onAuthChange(cb: (user: User | null) => void): () => void {
  if (!authInstance) {
    cb(null)
    return () => {}
  }
  return onAuthStateChanged(authInstance, cb)
}

/** Synchronous read of the current signed-in user's uid, or `null` if signed out or not
 * configured. Used to key the Firestore doc (`notes/{uid}`) in `cloud-adapter.ts`. */
export function getCurrentUid(): string | null {
  return authInstance?.currentUser?.uid ?? null
}

// ── Firestore document primitives ──────────────────────────────────────────────────
// Thin pass-throughs so `src/lib/sync/cloud-adapter.ts` (the only other file allowed to
// consume this module's Firebase-backed exports) never has to write
// `import ... from 'firebase/firestore'` itself. No notes-specific behavior lives here —
// the `notes/{uid}` collection name and document shape stay owned by `cloud-adapter.ts`;
// this is just "get a doc ref / read it / write it" with the wall's rules baked in
// (`setDocMerged` always merges, matching the "never silently overwrite" posture — a
// write here can only add/update fields, never wipe ones it doesn't mention).

export function getDocRef(
  db: Firestore,
  path: string,
  ...pathSegments: string[]
): DocumentReference<DocumentData> {
  return firestoreDoc(db, path, ...pathSegments)
}

export function setDocMerged(
  ref: DocumentReference<DocumentData>,
  data: Record<string, unknown>,
): Promise<void> {
  return firestoreSetDoc(ref, data, { merge: true })
}

/** Subscribes to a single document, with metadata changes included (needed so callers can
 * tell a cache-only/offline snapshot apart from a confirmed server one). Returns the
 * SDK's own `Unsubscribe` function. */
export function watchDocSnapshot(
  ref: DocumentReference<DocumentData>,
  onNext: (snapshot: DocumentSnapshot<DocumentData>) => void,
  onError: (error: FirestoreError) => void,
): Unsubscribe {
  const options: SnapshotListenOptions = { includeMetadataChanges: true }
  return firestoreOnSnapshot(ref, options, onNext, onError)
}

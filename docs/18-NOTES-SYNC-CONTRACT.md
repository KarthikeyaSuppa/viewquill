# Notes Sync Contract (desktop ↔ Android companion)

> **Why this doc exists.** Quillnight is ships an Android companion app (built
> separately, in Android Studio/Kotlin, on its own machine) whose only job is to keep a
> small personal "Notes" scratchpad in sync with the Quillnight Windows desktop app. The
> Android build happens **outside this repo**, by a different AI session with no access
> to the desktop/sidecar source — this doc is the entire contract that session needs: the
> wire format, the security posture, and worked Kotlin snippets. It is intentionally
> self-contained (do not assume the reader has read any other doc in this folder). If you
> are working *inside* this repo and need to change the desktop side of this contract,
> update this doc in the same change — it is the single source of truth for both ends.
>
> This feature is **not** the Story Library. It never touches Books, Scenes, Codex
> entries, images, or anything from `03-DATA-MODEL.md`. It is a single, small,
> free-text note field — closer to a sticky-note widget than to the writing app — that
> happens to live inside Quillnight for convenience. Treat it as an isolated subsystem.

## 0. The two notes, at a glance

Quillnight's Notes feature is actually **two completely independent notes**, each with
its own transport, its own storage, and its own last-write-wins clock:

| | Cloud note | LAN note |
|---|---|---|
| Works | Anywhere with internet | Only on the same Wi-Fi/LAN as the desktop |
| Backend | Firebase (Firestore + Firebase Auth) | The desktop app itself, acting as a tiny local HTTP server |
| Requires | Google sign-in | The desktop to be running and "Share on LAN" toggled on |
| Identity | Firebase Auth `uid` | A paired `device_token` issued by the desktop |
| Persists when desktop is closed | Yes (it's in the cloud) | No — the LAN server only exists while the desktop process is running and sharing |

An Android app can implement **either one, or both**. They do not interact with each
other at all — see §5 for why that separation is deliberate and must be preserved.

---

## 1. Cloud note (Firebase) — works anywhere

### 1.1 Backend shape

The desktop and Android app share **one Firebase project**. The desktop is already
registered in it as a web/desktop client; the Android app must be added to that **same**
project as a second, Android-platform app (Firebase Console → Project settings → Add
app → Android). Adding a platform to an existing project does not create a new project
or new data — both platforms read/write the same Firestore database.

- **Auth**: Firebase Authentication, Google sign-in provider. The signed-in user's
  Firebase Auth `uid` is the only identity that matters — it is not the app's local
  Quillnight profile system (`docs/13-PROFILES-AND-AUTH.md` on the desktop is a separate,
  fully local, unrelated concept). A user must sign in with the same Google account on
  both desktop and Android to see the same note.
- **Data store**: Cloud Firestore, **one document per user**:

  ```
  notes/{uid}
  ```

  where `{uid}` is exactly the Firebase Auth `uid` of the signed-in user. There is no
  sub-collection, no per-device document, no history — this is a single mutable document
  that both clients read and overwrite.

- **Document fields**:

  | Field | Type | Meaning |
  |---|---|---|
  | `content` | `string` | The full note text (the entire scratchpad, not a diff/delta). |
  | `updatedAt` | `number` | Epoch **milliseconds**, set by whichever client wrote last. This is the last-write-wins clock — see §1.3. |
  | `updatedBy` | `string` | A device identifier for the writer (see §1.4) — informational only, not used for conflict resolution. |
  | `schemaVersion` | `number` | Currently `1`. See §5.2 for the bump policy. |

  Example document:

  ```json
  {
    "content": "Buy milk\nCall Priya about the outline\n",
    "updatedAt": 1754730123456,
    "updatedBy": "desktop-9f3a2c",
    "schemaVersion": 1
  }
  ```

### 1.2 Security rules (already deployed by the desktop — do not assume Android needs to deploy anything)

The desktop side deploys these Firestore Security Rules to the shared project. Quote
them exactly — the Android app's requests must satisfy the same rule, there is nothing
extra for Android to configure:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /notes/{uid} {
      allow read, write: if request.auth != null && request.auth.uid == uid;
    }
  }
}
```

In plain terms: a signed-in user may only read/write **their own** `notes/{uid}`
document — never anyone else's. There is no admin/shared note, no way to share a note
between two Google accounts, and no anonymous access. If a future feature wants shared
notes, that is a rules change and a schema change — do not try to work around this by,
e.g., writing to another user's `uid` path from the client; it will simply be denied.

### 1.3 Sync semantics: last-write-wins by `updatedAt`

- Whenever either client applies a local edit, it writes the **entire** `content` string
  (not a delta/patch) plus a fresh `updatedAt = <current epoch ms>` and its own
  `updatedBy`.
- Whenever either client receives a remote update (via the realtime listener, see below)
  where the incoming `updatedAt` is **greater than** the last value it applied locally,
  it overwrites its local text with the incoming `content`. If the incoming `updatedAt`
  is less than or equal to what's already showing, the client ignores it (this also
  naturally deduplicates the client's own write echoing back to itself).
- **Important clock note**: the desktop writes `updatedAt` using its own local system
  clock in milliseconds (JavaScript `Date.now()`-equivalent), *not*
  `serverTimestamp()`/`FieldValue.serverTimestamp()`. The Android app **must match this**
  — use `System.currentTimeMillis()` when writing, and compare it as a plain number, not
  as a Firestore server timestamp type. Do not switch to `serverTimestamp()` on the
  Android side; a mismatched clock type would break the "higher wins" comparison because
  a server timestamp and a client-millis long are not directly comparable. This is a
  simple, deliberately unsophisticated LWW scheme — there is no vector clock, no CRDT,
  and no field-level merge. If both devices edit within the same second while offline,
  one edit will fully replace the other; this is an accepted tradeoff for a personal
  scratchpad, not a document editor.
- **Offline persistence**: both platforms should enable offline persistence so edits made
  without connectivity queue and sync once back online. On Android, Firestore's
  persistence is **enabled by default** since Firestore for Android SDK v24+ — no extra
  call is required to turn it on, but it can be explicitly configured (see §1.5) to be
  certain of the cache size/behavior.
- **Realtime updates**: both platforms should attach a snapshot listener on
  `notes/{uid}` so a note edited on one device appears on the other within a second or
  two while both are online, without a manual refresh.

### 1.4 What `updatedBy` should contain

Any stable-ish string identifying the writing device is fine — it is purely
informational (e.g. for a future "last edited on your phone" label) and is **never**
used in the LWW comparison. A reasonable choice on Android:
`"android-" + Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)`
truncated to a short id, or simply a random UUID generated once and persisted in
`SharedPreferences`/`EncryptedSharedPreferences`. Do not use anything that could be
considered a hardware identifier requiring special permission (e.g. IMEI) — `ANDROID_ID`
or a self-generated UUID is sufficient and requires no extra permission.

### 1.5 Android setup, step by step

1. **Add the Android app to the existing Firebase project** (Firebase Console → the
   Quillnight project → Project settings → "Add app" → Android icon). You will need the
   app's package name (choose one, e.g. `com.quillnight.notes` or whatever the Android
   project uses) and, for release builds later, a SHA-1/SHA-256 signing certificate
   fingerprint (required for Google Sign-In to work — debug builds need the debug
   keystore's fingerprint registered too, or Google sign-in will fail silently with a
   generic error).
2. Download the generated **`google-services.json`** and place it in the Android app
   module's root (`app/google-services.json`), exactly as Firebase's console instructs.
   This file is not secret in the sense of an API key that grants broad access — it is
   safe to check into the Android project's own repo (Firebase's own docs note this) —
   but it is still specific to this one project and should not be swapped for a
   different project's file.
3. **Gradle setup** (Kotlin DSL, `build.gradle.kts`):

   Project-level `build.gradle.kts`:
   ```kotlin
   plugins {
       id("com.google.gms.google-services") version "4.4.3" apply false
   }
   ```

   App-level `app/build.gradle.kts`:
   ```kotlin
   plugins {
       id("com.android.application")
       id("org.jetbrains.kotlin.android")
       id("com.google.gms.google-services")
   }

   dependencies {
       implementation(platform("com.google.firebase:firebase-bom:34.4.0"))
       implementation("com.google.firebase:firebase-auth-ktx")
       implementation("com.google.firebase:firebase-firestore-ktx")

       // Google sign-in via Credential Manager (current recommended API, 2026)
       implementation("androidx.credentials:credentials:1.5.0")
       implementation("androidx.credentials:credentials-play-services-auth:1.5.0")
       implementation("com.google.android.libraries.identity.googleid:googleid:1.1.1")
   }
   ```

   Use the Firebase BoM (`firebase-bom`) version current at build time rather than
   pinning individual Firebase artifact versions by hand — check
   https://firebase.google.com/support/release-notes/android for the latest BoM when you
   actually build this; the version above is illustrative, not gospel.

   > Note on the sign-in library: Google's older `GoogleSignInClient`
   > (`com.google.android.gms:play-services-auth`'s `GoogleSignIn.getClient(...)`) still
   > works but is in maintenance mode. The current recommended approach (and what the
   > snippet below uses) is **Credential Manager** with
   > `GetSignInWithGoogleOption`/`GoogleIdTokenCredential`, which is what Firebase's own
   > Android Auth documentation demonstrates as of the 2025–2026 SDKs. If Credential
   > Manager proves awkward in practice, falling back to the legacy `GoogleSignInClient`
   > and `Firebase Auth`'s `GoogleAuthProvider.getCredential(idToken, null)` is a fully
   > supported equivalent — the Firestore/LWW contract in §1.3 is identical either way;
   > only the sign-in call changes.

4. **Enable offline persistence explicitly (optional but recommended for clarity)**,
   once, e.g. in `Application.onCreate()`:
   ```kotlin
   Firebase.firestore.firestoreSettings = firestoreSettings {
       isPersistenceEnabled = true
   }
   ```

5. **Minimal Kotlin flow**: sign in → get `uid` → listen/write to `notes/{uid}`.

   ```kotlin
   // --- Sign-in (Credential Manager + Google ID + Firebase Auth) ---
   suspend fun signInWithGoogle(context: Context) {
       val credentialManager = CredentialManager.create(context)

       val googleIdOption = GetSignInWithGoogleOption.Builder(
           serverClientId = context.getString(R.string.default_web_client_id) // from google-services.json / Firebase console "Web client ID"
       ).build()

       val request = GetCredentialRequest.Builder()
           .addCredentialOption(googleIdOption)
           .build()

       val result = credentialManager.getCredential(context, request)
       val credential = GoogleIdTokenCredential.createFrom(result.credential.data)

       val firebaseCredential = GoogleAuthProvider.getCredential(credential.idToken, null)
       Firebase.auth.signInWithCredential(firebaseCredential).await()
       // Firebase.auth.currentUser!!.uid is now the note's document id
   }

   // --- Model + repository ---
   data class CloudNote(
       val content: String = "",
       val updatedAt: Long = 0L,
       val updatedBy: String = "",
       val schemaVersion: Int = 1
   )

   class CloudNoteRepository(private val deviceId: String) {
       private val db = Firebase.firestore

       private fun docRef(uid: String) = db.collection("notes").document(uid)

       /** Realtime updates; caller decides whether to apply based on updatedAt (LWW). */
       fun listen(uid: String, onUpdate: (CloudNote) -> Unit) {
           docRef(uid).addSnapshotListener { snapshot, error ->
               if (error != null || snapshot == null || !snapshot.exists()) return@addSnapshotListener
               val note = snapshot.toObject(CloudNote::class.java) ?: return@addSnapshotListener
               onUpdate(note)
           }
       }

       /** Local edit -> write full content with a fresh client-millis clock. */
       suspend fun save(uid: String, content: String) {
           val note = CloudNote(
               content = content,
               updatedAt = System.currentTimeMillis(), // NOT serverTimestamp() -- see §1.3
               updatedBy = deviceId,
               schemaVersion = 1
           )
           docRef(uid).set(note).await()
       }
   }

   // --- Wiring it together in a ViewModel (sketch) ---
   class NotesViewModel(private val repo: CloudNoteRepository) : ViewModel() {
       private var lastAppliedUpdatedAt = 0L
       val noteText = MutableStateFlow("")

       fun startListening(uid: String) {
           repo.listen(uid) { incoming ->
               if (incoming.updatedAt > lastAppliedUpdatedAt) {
                   lastAppliedUpdatedAt = incoming.updatedAt
                   noteText.value = incoming.content
               }
               // else: stale or an echo of our own write -- ignore
           }
       }

       fun onLocalEdit(uid: String, newText: String) {
           noteText.value = newText
           viewModelScope.launch {
               val writtenAt = System.currentTimeMillis()
               repo.save(uid, newText)
               lastAppliedUpdatedAt = writtenAt // so our own echo doesn't re-trigger a redundant apply
           }
       }
   }
   ```

   In real usage, debounce `onLocalEdit` (e.g. ~500ms after the user stops typing) rather
   than writing on every keystroke — Firestore has no rate limit that would break this,
   but it avoids needless writes and battery/network churn. The desktop side debounces
   similarly; there is no requirement that the two debounce intervals match.

---

## 2. LAN note — same Wi-Fi, no cloud, no account

This path does not touch Firebase at all. The desktop app, while the user has a "Share
on LAN" toggle turned on, runs a small local HTTP server that exposes **only** a single
note resource — nothing else in Quillnight is reachable this way (see §5.3). The Android
app is a plain HTTP client of that server.

### 2.1 Discovery / pairing

The desktop shows a **QR code** whenever LAN sharing is toggled on. The QR encodes a
JSON payload:

```json
{
  "v": 1,
  "host": "192.168.1.42",
  "port": 51820,
  "note_id": "default",
  "pairing_code": "483920",
  "fp": "b7:1a:...:9c"
}
```

| Field | Meaning |
|---|---|
| `v` | Wire-protocol version for this QR payload. See §5.2 for the bump policy. |
| `host` | The desktop's current LAN IP (IPv4, dotted-decimal). |
| `port` | The port the note server is listening on. Not necessarily stable across sessions — always read it fresh from the QR/manual entry, never hardcode a port. |
| `note_id` | Currently always the literal string `"default"` — reserved for a possible future multi-note LAN mode; treat it as an opaque string, don't parse it. |
| `pairing_code` | The same 6-digit code shown as human-readable text next to the QR, for manual entry when scanning isn't convenient. Short-lived (~120 seconds) and single-use. |
| `fp` | A short fingerprint/hash of the desktop's pairing secret, included so the phone can display "confirm this matches: b7:1a:...:9c" for out-of-band verification if desired. Optional to show in the Android UI; not required for the protocol to function. |

The Android app should offer **both** entry paths: scan the QR (fills in everything), or
manually type host + port + the 6-digit code (for when a camera isn't available or the
QR can't be scanned).

### 2.2 Pairing handshake

```
POST http://{host}:{port}/pair
Content-Type: application/json

{ "code": "483920" }
```

Response (200):
```json
{ "device_token": "k7f9c1e2b6a84d3f9e0c7b5a2d1f8e6c..." }
```

- The `pairing_code` is **short-lived** (~120 seconds from when the QR/code was
  generated) and **single-use** — once a pairing request succeeds, the desktop
  invalidates that code immediately, even if the phone somehow retries. If the code has
  expired or was already used, the desktop returns a 4xx and the user must regenerate a
  fresh QR/code on the desktop.
- The returned `device_token` is **long-lived** (it stays valid until the user revokes
  it from the desktop's sharing settings, or clears/disables LAN sharing entirely) and
  must be stored **securely** on Android — use `EncryptedSharedPreferences`
  (`androidx.security:security-crypto`) or the Android Keystore-backed equivalent, never
  a plain `SharedPreferences` file or a file on external storage. This token is the only
  long-term credential for this device; treat it with the same care as a password.
- One `device_token` is issued per successful pairing. If the user re-pairs the same
  phone later (e.g. after clearing app data), that's a new pairing flow producing a new
  token — old tokens are not looked up or reused.

### 2.3 Authenticated requests

Every request to `/note` (GET or PUT) must include:

```
Authorization: Bearer <device_token>
X-Quillnight-LAN: 1
```

and must **not** include an `Origin` header. The desktop deliberately rejects any
request that carries an `Origin` header at all, as a defense against DNS-rebinding and
"a webpage in a browser on this LAN quietly calls the note server" attacks — a real
native Android HTTP client (OkHttp) does not add an `Origin` header on its own, so this
requires no special handling in normal use. The one thing to actively avoid: do **not**
add an OkHttp `Interceptor` that injects an `Origin` header (there is no reason to; this
note calls it out only so nobody "helpfully" adds one while debugging with a browser-like
mental model). If the desktop ever responds with a rejection tied to this header, that is
a sign something in the HTTP stack (a proxy, a debugging tool, a misconfigured
interceptor) added an `Origin` header that shouldn't be there.

### 2.4 Reading and writing the note

```
GET http://{host}:{port}/note
Authorization: Bearer <device_token>
X-Quillnight-LAN: 1
```

Response (200):
```json
{
  "content": "grocery list...",
  "updated_at": 1754730123456,
  "updated_by": "desktop-9f3a2c"
}
```

```
PUT http://{host}:{port}/note
Authorization: Bearer <device_token>
X-Quillnight-LAN: 1
Content-Type: application/json

{
  "content": "grocery list...\nmilk\n",
  "updated_at": 1754730129999,
  "updated_by": "android-3fae91"
}
```

The `PUT` response echoes back the same shape (the server's accepted view of the note,
after applying it) — treat the response body as the new source of truth rather than
assuming the write was applied byte-for-byte:
```json
{
  "content": "grocery list...\nmilk\n",
  "updated_at": 1754730129999,
  "updated_by": "android-3fae91"
}
```

**Sync semantics are last-write-wins by `updated_at`, in epoch milliseconds** — identical
in spirit to the cloud note (§1.3), but this is a completely separate note with its own
clock/state; a value here has no relationship to `notes/{uid}`'s `updatedAt`. On Android,
compute `updated_at` with `System.currentTimeMillis()` at the moment of the local edit,
the same way as §1.3.

Notes on server availability:
- The desktop **only serves `/note` while the user has LAN sharing switched on** for that
  session. If sharing is off, or the desktop app isn't running, requests will simply fail
  to connect (connection refused/timeout) — the Android app should treat "can't reach the
  LAN server" as an expected, non-error state (show "not connected" rather than an alarm)
  since it's a completely normal condition whenever the user isn't near their desktop or
  hasn't turned sharing on.
- The first time the desktop binds its listening socket, **Windows Firewall may prompt
  the user** to allow the app through on the private network profile — this is a
  desktop-side, one-time OS prompt, not something the Android app can see or needs to
  handle, but it explains why a freshly-enabled toggle might not be reachable for a few
  seconds until the user answers that prompt.
- `host`/`port` can change between sessions (DHCP lease changes, the app choosing a new
  ephemeral port) — always re-derive them from a fresh QR scan/manual entry rather than
  caching last session's values as a fallback default.

### 2.5 mDNS (optional)

The desktop optionally advertises itself via mDNS/Bonjour under the service type
`_quillnight-note._tcp` for local network auto-discovery tooling. Since the QR payload
already carries the complete `host`/`port`/`pairing_code` needed to pair, implementing
mDNS discovery on the Android side is **optional** — it would only save the user from
scanning a QR on subsequent connections if the app chooses to build a "auto-detect on
same network" convenience feature later. It is not required for a correct, working
implementation of this contract.

### 2.6 Android networking setup

Because this is plain HTTP (no TLS) on a private local network, Android's default
cleartext-traffic block (`android:usesCleartextTraffic="false"` by default on API 28+)
must be relaxed **only for local-network addresses**, not globally. Use a scoped Network
Security Config rather than disabling cleartext protection app-wide:

`app/src/main/res/xml/network_security_config.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <!-- RFC1918 private ranges the desktop's LAN IP will fall in -->
        <domain includeSubdomains="false">10.0.0.0/8</domain>
        <domain includeSubdomains="false">172.16.0.0/12</domain>
        <domain includeSubdomains="false">192.168.0.0/16</domain>
    </domain-config>
</network-security-config>
```

`AndroidManifest.xml`:
```xml
<application
    android:networkSecurityConfig="@xml/network_security_config"
    ... >
```

Note: Android's `<domain>` element in a Network Security Config matches hostnames, not
CIDR ranges, in the strict spec sense — in practice OkHttp/the platform's cleartext check
is applied per literal IP string the socket connects to, so pin the exact `host` value
your app is about to connect to (from the QR) as the effective allowed literal, and treat
the CIDR-style entries above as documentation of *intent* (the private ranges you expect
`host` to fall within) rather than a guarantee the platform pattern-matches a CIDR block.
If a build finds the platform rejects a literal-IP domain entry, the pragmatic fallback
used by other LAN-pairing Android apps is a single catch-all
`<base-config cleartextTrafficPermitted="true">` scoped only to debug/local builds, or
validating `host` is a private-range address in app code before ever issuing the
cleartext request (defense in depth, since the LAN server itself already refuses anything
without a valid `device_token`).

### 2.7 Minimal Kotlin/OkHttp flow

```kotlin
data class PairResponse(val device_token: String)
data class LanNote(val content: String, val updated_at: Long, val updated_by: String)

class LanNoteClient(
    private val host: String,
    private val port: Int,
    private val deviceToken: String?, // null until paired
    private val deviceId: String
) {
    private val client = OkHttpClient() // do NOT add an Origin-header interceptor -- see §2.3
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()
    private val moshi = Moshi.Builder().build() // or kotlinx.serialization -- illustrative only

    private val baseUrl get() = "http://$host:$port"

    suspend fun pair(pairingCode: String): String = withContext(Dispatchers.IO) {
        val body = """{"code":"$pairingCode"}""".toRequestBody(jsonMediaType)
        val request = Request.Builder()
            .url("$baseUrl/pair")
            .post(body)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("Pairing failed: HTTP ${response.code}")
            }
            val adapter = moshi.adapter(PairResponse::class.java)
            val parsed = adapter.fromJson(response.body!!.string())
                ?: throw IOException("Empty pairing response")
            parsed.device_token
        }
    }

    private fun authedRequest(): Request.Builder =
        Request.Builder()
            .header("Authorization", "Bearer $deviceToken")
            .header("X-Quillnight-LAN", "1")
            // deliberately never set an Origin header here

    suspend fun getNote(): LanNote = withContext(Dispatchers.IO) {
        val request = authedRequest().url("$baseUrl/note").get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("GET /note failed: HTTP ${response.code}")
            moshi.adapter(LanNote::class.java).fromJson(response.body!!.string())
                ?: throw IOException("Empty note response")
        }
    }

    suspend fun putNote(content: String): LanNote = withContext(Dispatchers.IO) {
        val payload = LanNote(
            content = content,
            updated_at = System.currentTimeMillis(),
            updated_by = deviceId
        )
        val json = moshi.adapter(LanNote::class.java).toJson(payload)
        val request = authedRequest()
            .url("$baseUrl/note")
            .put(json.toRequestBody(jsonMediaType))
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("PUT /note failed: HTTP ${response.code}")
            moshi.adapter(LanNote::class.java).fromJson(response.body!!.string())
                ?: throw IOException("Empty note response")
        }
    }
}
```

Apply the same last-write-wins comparison shown in the §1.5 `NotesViewModel` sketch: keep
a `lastAppliedUpdatedAt` per note (cloud and LAN notes each get their own — do not share
one variable between them), and only apply an incoming `updated_at`/`content` if it is
strictly greater than the last value this client has already shown.

---

## 3. Which note is which (do not conflate them)

- The **cloud note** (`notes/{uid}` in Firestore) and the **LAN note** (the desktop's
  `/note` HTTP resource) are **two entirely separate pieces of storage with two separate
  clocks**. Editing one never reads from, writes to, or resets the other.
- A Quillnight desktop user could plausibly use only one of the two, both, or neither —
  the Android app's UI should make it clear at all times which note a given screen is
  showing (see §6's suggested two-tab layout).
- There is no server-side or client-side bridging logic that copies content between them.
  If a future version wants that, it is a new, explicit feature — do not build it by
  quietly wiring the two `updatedAt`/`updated_at` clocks together; that would violate the
  "never silently overwrite" principle these notes should still honor even though they
  are a lightweight feature (see §5.1).

---

## 4. What the desktop side guarantees

- **Only the note leaves the desktop machine, nothing else.** The LAN server exposes
  exactly two endpoints (`/pair`, `/note`) and nothing else in Quillnight — no Story
  Library data, no Codex, no images, no settings, no Groq API key, are reachable over
  LAN, ever, under any endpoint. The Firebase cloud path is similarly scoped: the
  Firestore security rules in §1.2 only grant access to `notes/{uid}`; there is no other
  collection in that project the desktop writes app data to.
- **Everything else Quillnight stores is fully local** to the desktop's SQLite database
  and stays there. The Notes feature is a deliberately narrow, bolted-on exception to the
  app's otherwise fully-local posture (see `08-AI-PROVIDER-MODES.md`'s "local-first" data
  posture for the same design instinct applied to AI calls) — it exists because a
  personal scratchpad genuinely benefits from being reachable from a phone, unlike the
  actual manuscript data.
- **LAN sharing is opt-in per session** (the user must toggle it on) and **stops being
  reachable the moment it's toggled off or the desktop app closes** — there is no
  background always-on listener.
- **Pairing codes expire and are single-use**; **device tokens can be revoked** from the
  desktop's sharing settings, at which point that phone's stored token stops working on
  its next request (expect a 401/403 — treat this as "please re-pair," not a crash).

---

## 5. Cross-cutting policy

### 5.1 The "never lose data, never silently overwrite" rule applies here too

Quillnight's project-wide rule — *AI and sync never silently overwrite user text; the
user's own words are never dropped without them seeing it happen* — is written with AI
transforms in mind, but the spirit applies to this sync feature as well, even though the
mechanism here is a plain LWW clock rather than an Accept/Reject diff:

- Last-write-wins is an accepted, intentional simplification for a lightweight personal
  scratchpad (§1.3), not an oversight — but the Android app should still make it obvious
  to the user which note they're looking at and roughly when it last changed (surface
  `updatedAt`/`updated_at` as a "last updated" timestamp in the UI), so a stale-looking
  note is visible as stale rather than silently trusted.
- Do **not** build any feature on top of this contract that discards local edits without
  the LWW comparison actually running (e.g. don't add a "pull to refresh that force-
  overwrites local text regardless of timestamp" shortcut) — that would reintroduce a
  silent-overwrite bug this doc is specifically trying to avoid.

### 5.2 Versioning policy

- **Cloud note `schemaVersion`** (currently `1`): bump only when the **document field
  shape** changes in a backward-incompatible way (e.g. renaming `content`, splitting the
  note into multiple fields, changing `updatedAt`'s type away from epoch-millis number).
  A client reading a document with a `schemaVersion` higher than it understands should
  refuse to blindly overwrite it (show a "this note was updated by a newer app version"
  message) rather than coercing/guessing at the new shape.
- **LAN QR `v`** (currently `1`): bump only when the **QR payload shape** or the
  **HTTP wire protocol** (`/pair` or `/note` request/response shape, required headers)
  changes incompatibly. An Android build that doesn't recognize a scanned QR's `v` should
  refuse to attempt pairing and show a "please update the app" style message rather than
  guessing at fields that might not exist.
- Both version fields are intentionally simple integers, not semver strings — treat any
  version number higher than the one this doc describes as "unknown, don't guess," and
  treat this doc itself as needing an update the next time either number changes.

### 5.3 Scope guarantee, restated

To be unambiguous for whoever builds the Android app from this doc alone: implementing
this contract gives the Android app access to **exactly** the note content described
above, and nothing else about the user's Quillnight data. There is no endpoint, field, or
QR payload anywhere in this contract that exposes Books, Scenes, Codex entries, images,
draft exports, settings, or credentials. If a future task asks the Android app to also
show, say, a list of the user's Books, that is a materially different, larger feature
requiring new backend endpoints, new security review, and almost certainly a new version
of this doc — it is explicitly out of scope for "the Notes companion app."

---

## 6. Suggested Android app UX (minimal, not prescriptive)

A minimal but complete implementation of this contract needs only:

1. **Two tabs/panes**: "Wi-Fi Note" (LAN) and "Cloud Note" (Firebase) — clearly labeled
   so the user always knows which of the two independent notes (§3) they're editing.
2. **A pairing/scan screen** for the LAN tab: a camera-based QR scanner (e.g.
   `androidx.camera` + a barcode-scanning library such as ML Kit's barcode scanning API,
   or any maintained QR library) plus a manual-entry fallback form (host, port, 6-digit
   code) for when scanning isn't practical. Once paired, this screen doesn't need to be
   shown again until the stored `device_token` is rejected (§4) or the user chooses to
   re-pair/unpair.
3. **A Google sign-in button** for the Cloud tab, using the Credential Manager flow from
   §1.5 — once signed in, the note loads and stays live via the snapshot listener; no
   further chrome is required beyond a simple text editor and a "last updated" caption.
4. Each pane is otherwise just a single multi-line text field bound to that note's
   `content`, with the debounced local-edit → write flow from §1.5/§2.7, and a small
   connectivity indicator (paired/not paired for LAN; signed-in/signed-out for Cloud).

Everything beyond this (offline queuing UI, conflict history, rich text, multiple named
notes) is intentionally out of scope for the minimal version of this contract — build the
above first, confirm both sync paths work end-to-end against a real desktop instance,
then treat anything further as a new, separately-scoped feature.

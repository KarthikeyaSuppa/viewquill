# Firebase provisioning — Notes cloud sync (T7+T8)

This is a from-zero checklist for someone who has **never used Firebase
before**, to set up the one Firebase project that backs Quillnight's
optional Notes-tab cloud sync (desktop today; the same project is meant to
be reused by the future Android app — see step 1).

Scope reminder: this project is used for exactly one thing — syncing the
single "cloud note" scratchpad on the Notes tab, keyed by
`notes/{signed-in Google uid}`. Nothing else in Quillnight (Books, Codex,
canvas, drafts, images) ever touches this project or any network at all.

## 1. Create the Firebase project

1. Go to <https://console.firebase.google.com/> and sign in with the Google
   account you want to own this project (this can be a personal account —
   it doesn't need to be an organization).
2. Click **Add project**. Give it a name (e.g. `quillnight-notes`). You can
   decline Google Analytics — it isn't needed for this feature.
3. **Use this same project for the future Quillnight Android app.** Don't
   create a second project later for Android — Firestore's security rules
   below are already scoped per-signed-in-user (`request.auth.uid`), so the
   same project safely serves both a desktop and a phone client for the same
   Google account's note.

## 2. Enable Cloud Firestore

1. In the left nav, click **Build → Firestore Database**.
2. Click **Create database**.
3. Choose **Native mode** (not Datastore mode).
4. Pick any region close to you — this only affects latency, not
   functionality.
5. For the initial ruleset, either option is fine — you'll overwrite it with
   `firestore.rules` (this folder) in step 5.

## 3. Enable Google sign-in

1. Left nav → **Build → Authentication**.
2. Click **Get started** if this is the first provider you're enabling.
3. Go to the **Sign-in method** tab, click **Google**, toggle it **Enable**,
   pick a support email, and **Save**.

## 4. Add `localhost` as an authorized domain

1. Still in **Authentication**, go to **Settings → Authorized domains**.
2. Confirm `localhost` is in the list (Firebase usually adds it by default
   for new projects — if not, click **Add domain** and add it).
3. This is required for Google sign-in's popup flow to work against the
   desktop app's local dev server (`http://localhost:1420`). When the app is
   later packaged with Tauri, revisit this — a packaged app's origin may
   need adding too (out of scope for this task; noted for the installer
   phase).

## 5. Deploy the Firestore security rules

The rules live at `apps/desktop/firebase/firestore.rules` in this repo:

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

They mean: a signed-in user can only ever read or write their **own**
`notes/{uid}` document (`uid` must equal `request.auth.uid`) — nobody can
read or write anyone else's note, and a signed-out request can't touch
anything.

To deploy, easiest path (no Firebase CLI install needed):

1. In the console, go to **Firestore Database → Rules**.
2. Paste the contents of `firestore.rules` in, replacing whatever's there.
3. Click **Publish**.

(If you do have the Firebase CLI set up elsewhere, `firebase deploy
--only firestore:rules` from a directory with a matching `firebase.json`
works too — not required for this checklist.)

## 6. Register a Web app and copy its config

1. Left nav → gear icon → **Project settings**.
2. Under **Your apps**, click the **Web** icon (`</>`) to register a new web
   app. Give it any nickname (e.g. `quillnight-desktop`). You don't need
   Firebase Hosting.
3. Firebase shows a `firebaseConfig` object like:

   ```json
   {
     "apiKey": "AIzaSy...",
     "authDomain": "quillnight-notes.firebaseapp.com",
     "projectId": "quillnight-notes",
     "storageBucket": "quillnight-notes.appspot.com",
     "messagingSenderId": "123456789012",
     "appId": "1:123456789012:web:abcdef1234567890"
   }
   ```

   This `apiKey` is a **publishable client identifier, not a secret** —
   it's safe to have in this JSON blob; the security rules from step 5 are
   what actually protect the data, not hiding this value.

4. Copy the whole JSON object (including the outer `{ }`).

## 7. Paste it into Quillnight

1. Open Quillnight → **Settings → Notes**.
2. Paste the JSON into the "Firebase web config" box.
3. Click **Save**. The badge should flip to "Configured ✓".
4. Go to the **Notes** tab → the Cloud pane should now show a
   "Sign in with Google" button instead of the "connect a project" card.
5. Sign in — you should see your note start syncing (status line under the
   textarea reads "Saved"/"Syncing…").

## Troubleshooting

- **"Your browser blocked the sign-in popup"** — allow popups for this app
  and click Sign in again.
- **Sign-in succeeds but the note never leaves "Syncing…"/shows "Sync
  error"** — double check step 5's rules were actually **published** (not
  just pasted into the editor), and that step 4's `localhost` authorized
  domain is present.
- **Badge stays "Not configured" after Save** — the pasted JSON is missing
  one of `apiKey`/`projectId`/`appId`, or isn't valid JSON. Re-copy the
  config object from step 6 verbatim, including the outer braces.

## On a restricted / corporate network

Cloud sync reaches out to Google (`*.googleapis.com`, `*.firebaseapp.com`).
A managed/work machine or network can interfere in ways that are **not bugs in
Quillnight** — the note store code is the same either way; only the transport
is blocked. If cloud sync misbehaves on a corporate setup, check:

- **TLS inspection / DLP proxy** — corporate proxies that re-sign HTTPS can
  break the Firebase SDK's live connection to Firestore (the note stays on
  "Syncing…"). Testing on a personal network avoids this.
- **Google sign-in is SSO-restricted** — a corporate Google account may refuse
  to sign in to a personal Firebase project, or block the sign-in popup by
  policy. Use a **personal** Google account for both the Firebase project and
  sign-in.
- **Console access blocked** — `console.firebase.google.com` itself may be
  filtered; do the one-time provisioning (steps 1–6) on an unrestricted
  machine/account.

**LAN sync ("On your Wi-Fi") on a corporate machine** has its own gotchas,
separate from Firebase:

- **Windows Firewall** prompts when sharing first turns on (the app binds a
  local port). On a locked-down machine you may not have rights to approve it —
  if sharing won't start, this is the usual cause.
- **Client isolation** — most corporate/guest Wi-Fi blocks device-to-device
  traffic, so the phone can't reach the desktop even after pairing. LAN sync is
  intended for a **home/trusted network**; it will not work over a corporate AP
  with isolation enabled.

None of this affects the rest of Quillnight: Books, Codex, canvas, and drafts
are fully local and never touch the network regardless of these settings.

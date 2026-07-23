# Profiles & Local Auth

Added after Phase 2 at the user's request: **up to two local profiles**, each with its own
username + password, an avatar picker at launch (Netflix-style), and a "switch profile"
control inside the app. This document records the settled decisions so they aren't
re-litigated; it is additive to the original 12 spec docs.

## What this is — and isn't

- **A UI/profile lock, not encryption.** The live SQLite database stays **plaintext on disk**
  (the deliberate tradeoff in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md)
  — "Live database unencrypted, only exports encrypted"). A profile password gates the UI and
  selects who is writing; it does **not** protect the files against anyone with disk access.
  Real at-rest protection remains OS full-disk encryption + the encrypted `.quillproj` exports.
  No UX copy should imply the password encrypts data.
- **Still fully local / offline.** No cloud accounts, no telemetry — consistent with Offline
  mode. "Accounts" here means local OS-independent profiles in the app's own SQLite file.

## Core decision: two profiles SHARE one library

The single Story Library stays shared across both profiles — books, scenes, codex, and images
remain canonical and reusable (the founding premise in [01-PRODUCT-VISION.md](01-PRODUCT-VISION.md)).
Profiles are **not** data silos. Rejected: separate per-profile libraries (would force an
`owner_id` onto every table and scope every query/endpoint — heavy, and it fights the reuse
premise for a personal app). If a genuinely private second library is ever needed, that is a
separate, larger change.

**What differs per profile:** avatar, and the *personal* settings — reading typography
(font/size/spacing/line-length/ruler), theme (day/night/auto), delight level, sounds, mascot,
and `onboarding_complete` (so each profile runs its own Reading Comfort Wizard). Writing
streaks / word goals are per profile (`writing_sessions.user_id`, wired in Phase 8).

**What stays shared (global):** AI provider settings — `ai_mode`, model names, `groq_*`,
dictation/STT engine. The Groq key remains the in-memory seam (never persisted; see
[08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md)).

## Data model additions

```sql
CREATE TABLE users (
  id            TEXT PRIMARY KEY,              -- UUID
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,                 -- argon2 encoded string; never logged/returned
  display_name  TEXT,
  avatar        TEXT,                          -- preset id (e.g. "fox"); no image upload in v1
  created_at    TEXT NOT NULL,
  is_active     INTEGER NOT NULL DEFAULT 1
);
```

`app_settings` gains per-user scoping (was `key` PK, now a surrogate `id` + nullable `user_id`):

```sql
-- id TEXT PK | user_id TEXT NULL FK users(id) ON DELETE CASCADE | key TEXT NOT NULL | value JSON
-- Partial unique indexes keep both a single global row per key and one row per (user,key):
--   UNIQUE(user_id, key) WHERE user_id IS NOT NULL
--   UNIQUE(key)          WHERE user_id IS NULL
```

Existing settings rows migrate to `user_id = NULL` → they become the shared/global defaults
(no data loss). Merge order at read time: `DEFAULT_SETTINGS` → global rows (`user_id IS NULL`)
→ the current user's rows. Writes route by an explicit `PER_USER_KEYS` set (the personal
settings above); everything else writes the global row.

`writing_sessions` gains `user_id TEXT NULL FK users(id) ON DELETE SET NULL` (column provisioned
now; streak endpoints are Phase 8).

Delivered as a single Alembic revision (`down_revision = 9cc2ce21fa1e`), SQLite-batch style,
with a verified downgrade→upgrade round-trip.

## Auth mechanics

- **Password hashing:** `argon2-cffi` (`argon2.PasswordHasher`). Never store or log plaintext.
- **Sessions:** an in-memory `{token → user_id}` map (token = `secrets.token_urlsafe`). The
  frontend holds the token in a Zustand store (memory only) and sends `Authorization: Bearer
  <token>`. A sidecar restart clears sessions — intended, since relaunch shows the picker.
  Rejected: JWT (needs a signing secret; expiry/refresh buys nothing on a single local host)
  and a persisted `sessions` table (we *want* re-pick on relaunch).
- **What is protected:** only `GET/PATCH /settings`, `GET /auth/me`, `POST /auth/logout`, and
  future streak endpoints require `get_current_user`. `GET /profiles`, `POST /profiles`, and
  `POST /auth/login` are public (needed to render the picker / first run / login). The library
  endpoints (`/books /scenes /canvas /codex /llm /voice`) stay **open** — the library is shared
  and "must be logged in to use the app" is enforced by the client-side ProfileGate, not by
  per-endpoint authorization. Bolting auth onto every route would add surface for no real gain
  on a shared-library local app.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/profiles` | public | list profiles for the picker (id, username, display_name, avatar — never the hash) |
| POST | `/profiles` | public | create a profile (max 2, unique username); hashes the password |
| POST | `/auth/login` | public | verify username+password → returns a session token |
| GET | `/auth/me` | bearer | current profile |
| POST | `/auth/logout` | bearer | invalidate the current token |
| GET/PATCH | `/settings` | bearer | now per-user (personal keys) + global (shared keys) |

## Frontend flow

1. `BootGate`: sidecar health → if no session token, render the **ProfileGate**, else the app.
2. **ProfileGate**: a glass, avatar-based picker of existing profiles; an "add profile" tile
   shown only while count < 2; first-run create form (username + password + pick a preset
   avatar); a login form (password) for a chosen profile.
3. On login, the `['settings']` query is invalidated so theme/reading/delight immediately
   follow the profile.
4. The sidebar gains a **"Switch profile"** control that clears the session and returns to the
   picker.

## Review gates

Password hashing, the sessions layer, the profiles/auth router, and the per-user settings
isolation each get a `reviewer` pass (per [CLAUDE.md](../CLAUDE.md)); the migration's row
preservation is verified by a downgrade→upgrade round-trip before the feature is marked done.

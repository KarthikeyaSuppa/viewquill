# PHASE8.md — Phase 8 (Design/accessibility deep pass + reading aids + Lottie overhaul) Directive

Loaded for Phase 8. Status: **Built + audited (2026-07-28)**. Kept as historical record.

## 1. Context

Scope per docs/06-ROADMAP.md's Phase 8 paragraph, revised mid-planning by the user: cut
streaks/daily-word-goal/inkwell-ring gamification entirely (this is a storyboarding tool,
not a habit-tracker) and replaced with a **Lottie-based animation overhaul** for
lag-free, polished character animation across existing UI. Full plan (task list,
sequencing, budget) is in the approved plan file; not re-duplicated here beyond outcomes.

Kept from the original scope: WCAG AA audit, dyslexia-settings soak test, reading ruler +
focus mode, read-aloud karaoke, full Calm/Standard/Playful delight-matrix compliance.

## 2. Execution protocol (carried, user-confirmed)

- PLAN in main-session Plan Mode (Opus architect). User rejected the first draft
  (streaks), redirected via clarifying questions, plan re-drafted and approved.
- IMPLEMENT via builder (Sonnet) subagents, 1 scoped task (1–3 files) each, run in
  parallel across independent groups (A/B/E started immediately; C/D followed once the
  manuscript-reader keystone landed).
- REVIEWER (Opus) gate on `lib/speech.ts` only — the one file in this phase with a
  local-first risk (WebView2 online voices could leak manuscript text off-device).
- DEBUGGER (Sonnet) for the long-text soak test, which found and fixed one real
  performance issue.
- Main session ran the phase demo checklist itself where possible (no subagent) — see §6
  for what could and couldn't actually be confirmed from this environment.

## 3. What shipped

**Settings/theme (Group A):** `focus_mode` setting, 4 discrete `BG_TINTS` presets +
picker UI, `theme_mode: 'auto'` now re-evaluates on a timer/visibilitychange instead of
only at load.

**Manuscript reader (Group B, keystone):** the Draft tab had no rendered prose at all
before this phase. New `GET /books/{id}/draft-preview` (read-only, reuses
`export_service.build_compiled_document`, never touches export.py) + `<ManuscriptReader>`
— renders into the existing `.manuscript` class with globally-sequential
`data-para-index`/`data-w`/`data-c` attributes that every downstream reading-aid depends
on for exact positioning.

**Reading aids (Group C):** `useReadingCursor` (pointer + arrow-key line tracking, later
perf-fixed — see §5), reading ruler (Grey Bar / Shade, `R` toggle), focus mode (`F`
toggle, dims non-current paragraphs), both documented in the in-app Help guide.

**Read-aloud karaoke (Group D):** `lib/speech.ts` Web Speech wrapper — hard-filtered to
`voice.localService === true`, no fallback to any remote voice ever, reviewer-cleared
(see §5) — plus the toolbar/highlight component and a Settings Voice section (picker +
rate, degrades to a plain "no local voices" note rather than ever falling back remote).

**Lottie animation overhaul (Group E):** `lottie-react` added, a `<LottiePlayer>` wrapper
centralizing delight-level/reduced-motion gating (freezes on frame 0 at Calm/reduced-motion,
never a competing second gate), 4 curated CC0/free-tier Lottie assets
(`apps/desktop/src/assets/lottie/`, licenses recorded in `LICENSES.md`) swapped into: the
firefly mascot (replacing its old CSS/Motion glow), a new Playful-only delight-moment
accent layered alongside existing confetti calls, empty-state illustrations
(library + canvas), one loading spinner (manuscript reader), and the onboarding wizard
header.

**Audits (Group F):** WCAG AA contrast audit found and fixed one real Night-theme
failure (default button/badge text 3.39:1 → 5.49:1, verified via actual OKLab→luminance
math, not eyeballing); canvas keyboard audit found and fixed a real dead-end (Enter did
nothing on a focused node — now opens the editor, Escape returns focus correctly) plus
added the missing focus ring; shell/dialog audit added a missing skip-to-main link and
one missing nav focus ring (dialogs and drag-and-drop keyboard support were already
correct); delight-matrix verification found zero bypasses — every new animated surface
correctly routes through the live `useDelight()` hook; long-text soak test (80k words/40
chapters, synthetic seed script) found the backend fast (66ms/472KB draft-preview
response) and found one real frontend perf issue (see §5).

## 4. Reviewer gate outcome

`lib/speech.ts` (Web Speech local-voice-only guarantee): **no MUST-FIX**. Traced every
`speak()` call site, the zero-local-voices short-circuit, the cancel/stale-callback guard,
and confirmed no exfiltration side-channel. 2 SHOULD-FIX robustness gaps (missing
`onerror` handler on the terminal utterance; `speak([])` never resolving) — both fixed in
a small follow-up task, re-verified clean.

## 5. Bugs found and fixed during this phase (not part of the original task list)

- **Night-theme WCAG AA failure**: `--primary-foreground`/`--sidebar-primary-foreground`
  on `--primary` fill was 3.39:1 (needs 4.5:1) — affects the default Button/Badge, active
  sidebar nav, switch thumb, skip-to-content link. Fixed by darkening only the foreground
  token (reusing an existing dark tone already in the palette), not the fill color, since
  `--primary` is also used standalone as link/accent text elsewhere and darkening it would
  have broken that pairing.
- **Canvas keyboard dead-end**: React Flow's own node keydown handler never invoked the
  app's `onNodeClick` — Tab could reach a node but Enter did nothing. Fixed by adding a
  keydown handler on the canvas container scoped to the node-wrapper target only (so it
  doesn't hijack Enter on buttons inside each card).
- **Missing skip-to-main link and nav focus ring** in `app-shell.tsx` — added both,
  reusing the existing focus-ring utility rather than inventing one.
- **`useReadingCursor` layout-thrash**: re-queried and re-measured (`getBoundingClientRect`)
  every `[data-para-index]` element on every mousemove frame — full DOM scan + ~2000 forced
  layout reads at up to 60fps on an 80k-word document. Fixed by caching paragraph rects
  once (re-cached on mount, `ResizeObserver`, `MutationObserver` on content swap, and a
  window-resize backstop) and binary-searching the cached, sorted array instead — hot path
  is now one container-rect read plus O(log n) lookup, no scroll listener needed since
  offsets are container-relative and the surface doesn't scroll internally.

## 6. Demo checklist outcome (docs/06 §Phase 8, revised bar)

This build environment has no browser/screenshot tool available to the main session, so
visual/interactive confirmation of animation smoothness and rendering was **not**
possible to verify directly here, unlike Phase 7's demo (which was pure API calls). What
*was* confirmed from this environment:

1. `GET /books/{id}/draft-preview` verified live against the real Story Library (read-only,
   no writes) — returns correctly, confirming the manuscript-reader's backend keystone
   works end-to-end on real data, not just seeded test fixtures.
2. Every animated surface's delight-level gating was verified by direct code trace
   (Group F, delight-matrix task) to genuinely route through the live `useDelight()` hook
   with no bypass — this is the strongest evidence available short of an actual visual
   check that "Calm silences everything with no reload" holds.
3. Font/spacing-on-manuscript, ruler-follows-cursor, karaoke word-highlight, and Lottie
   mascot smoothness are all traceable in code (exact `data-c`/`data-w` offset math
   verified by two independent builder tasks cross-checking the same regex-based
   tokenization) but **require a manual look in the actual running app** to fully confirm
   per docs/06's demo bar. Flagging this explicitly rather than claiming a check that
   didn't happen.

## 7. Process carry-over

Next phase: Phase 9 (Hardening + installer), which also picks up the deferred periodic
backup timer (docs/14 §B2) and the two docs/14 "Phase 8"-tagged canvas items (templates,
keyboard-first node creation) that were deliberately deferred out of this phase to
protect budget. Continue prioritizing token/cost savings — this phase's ~35 background
agent calls stayed on Sonnet builders/debugger with exactly one Opus reviewer call.

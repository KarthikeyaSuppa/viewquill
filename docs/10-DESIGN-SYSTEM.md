# Design System — "Quill by Day, Night by Heart"

Quillnight's interface has two jobs that usually fight each other: be a **serious, evidence-based reading environment** for a dyslexic writer doing long sessions, and be **genuinely joyful** — playful, kid-like, alive. The resolution is one hard rule, stated up front and repeated wherever it applies:

> **Playfulness lives in the chrome, never inside the manuscript.** The text you read and write is always rendered in the calm, evidence-tuned reading environment. Mascots, confetti, sparkles, and sounds happen around it — never on top of your words.

Everything in this document respects `prefers-reduced-motion` (via Motion's `<MotionConfig reducedMotion="user">` app-wide, `motion-reduce:` Tailwind variants, and `disableForReducedMotion` on confetti), and every delight element is individually toggleable regardless of the global Delight Level.

---

## 1. The dual theme: Day / Night

The app's name is the theme system. Two first-class themes, switchable manually or automatically by local time (optional setting):

| Token | ☀ Day — "paper studio" | 🌙 Night — "cinematic studio" |
|---|---|---|
| Background | Cream `#FBF5E9` | Soft gray `#1E1E24` (never pure black) |
| Text | Near-black warm gray `#2A2721` | Off-white `#E8E6E1` (contrast deliberately a notch below maximum to limit halation/glare) |
| Accent | Warm amber/ink blue | Firefly gold `#FFC94D` + cool cyan |
| Ambient character | Subtle paper grain | Drifting firefly particle(s) on the canvas (Delight ≥ Standard) |

Why cream, specifically: the British Dyslexia Association style guide advises off-white over pure white (glare), and Rello & Bigham (ASSETS 2017, n=341) found warm backgrounds (peach/orange/yellow) measurably improved reading speed, most strongly for dyslexic readers. A **user-adjustable warm background tint** slider (cream → peach presets) ships in settings. Framing matters: this is a *comfort preference with evidence behind warm backgrounds*, **not** an "Irlen filter" — colored overlays as a dyslexia *treatment* are a debunked neuromyth (Henderson et al. 2011 and later systematic reviews), and the app makes no therapeutic claims.

Dark mode has no dyslexia-specific evidence either way; it's offered because long night sessions are real and the cinematic identity wants it. **Default: Day (cream) for the manuscript-heavy views; the user picks in onboarding.**

## 2. Typography

The single strongest research finding (Wallace et al. 2022, TOCHI, n=352): **font effectiveness is individual** — readers were ~35% faster in their best font than their worst, and *stated preference predicted actual performance only 18% of the time*. So Quillnight doesn't bet on one font; it measures.

- **Font picker** (all from Fontsource npm packages — official registry, self-hosted, no CDN calls): **Lexend** (default — its generous spacing and variable width axis embody the spacing evidence below, though its own reading studies are small-sample and creator-affiliated), **Atkinson Hyperlegible Next** (Braille Institute, Feb 2025, SIL OFL 1.1, variable weight 200–800, 150+ languages, plus a Mono sibling for screenplay elements), **OpenDyslexic** (option only — studies show no speed/accuracy benefit, but preference is legitimate; **never the default**), **Inter**, and system serif.
- **The 60-second font self-test** (part of the Reading Comfort Wizard, §7): the app shows the same short passage in each candidate font, times comfortable reading (self-paced tap-through), and recommends the fastest — because preference ≠ performance, measuring beats asking.

### Reading layout defaults (BDA Style Guide 2023 + Zorzi et al. 2012 PNAS)

Extra letter spacing has the best peer-reviewed evidence of any typographic intervention (reduces visual crowding). All values are live-adjustable via sliders; these are the defaults and ranges:

| Setting | Default | Range |
|---|---|---|
| Font size | 18px | 16–28px |
| Line height | 1.5 | 1.2–2.0 |
| Letter spacing | 0.035em (~BDA's 35%-of-letter-width guidance) | 0–0.12em |
| Word spacing | ≥3.5× letter spacing | linked to letter spacing |
| Line length | 65ch (`max-w-[65ch]`) | 45–80ch |
| Alignment | Left, **never justified** | — |
| Emphasis | **Bold only** — no italics, no ALL-CAPS in UI copy | — |

## 3. Reading aids

- **Reading ruler** — evidence-backed (Adobe's CHI 2023 study, 91 dyslexic + 86 non-dyslexic readers: Grey Bar, Shade, and Underline designs increased dyslexic reading speed and were preferred). Quillnight implements **Grey Bar** and **Shade** as a caret/pointer-following translucent overlay band (1–3 lines tall, adjustable opacity), custom-built (no dominant React library exists — existing implementations are browser extensions). Default **off**, one-key toggle (`R`), remembered per user.
- **Focus mode** — dims everything except the current paragraph; combines with the ruler.
- **Bionic Reading — deliberately NOT included.** A 2,074-reader test (Readwise 2022) and a peer-reviewed eye-tracking study ("No, Bionic Reading does not work," Acta Psychologica 2024) both found no speed or comprehension benefit, and the technique is trademarked/licensed. Recorded here so it doesn't get re-proposed later.
- **Read-aloud (karaoke mode)** — full design in [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md): Web Speech API word-by-word highlighting for proofreading; Piper neural voice for quality listen-through.

## 4. Dyslexia-aware spellcheck (a gap mainstream apps miss)

Standard spellcheckers fail dyslexic writers twice: phonetic misspellings ("fizishan" → physician) often produce no useful suggestions, and real-word errors (their/there, form/from) produce no squiggle at all. The stack (all open-source, sidecar-side):

- **Phonetic matching**: Hunspell with a PHONE table (metaphone-style) and/or **SymSpell** for fast frequency-ranked suggestions that tolerate heavy misspelling.
- **LanguageTool** for context/real-word errors — the errors dyslexic writers actually make. Runs locally (Java or the HTTP server variant); also doubles as the *external verifier* in the AI refine loop (see [11-AI-INTELLIGENCE.md](11-AI-INTELLIGENCE.md) — small models can't reliably self-critique, but they can fix what a deterministic checker flags).
- **Personal dictionary** (`personal_dictionary` table) — character names, invented lore words, so Elyndra stops getting squiggled.
- Later option (v2.0): word-prediction with phonetic support — Evmenova et al. 2010 showed it improves spelling and composition for struggling writers.

## 5. The delight stack (verified packages, July 2026)

| Purpose | Package | License | Notes |
|---|---|---|---|
| Core animation | `motion` (import `motion/react`) | MIT | v12+, the standard; layout animations, `AnimatePresence`, springs; `LazyMotion` keeps it ~6kB; `<MotionConfig reducedMotion="user">` app-wide |
| List/DOM micro-animations | `@formkit/auto-animate` | MIT | Zero-config FLIP on scene/chapter lists; its enable/disable handle wires straight to the Delight toggle |
| **Mascot** | `@rive-app/react-canvas` | MIT (runtime) | State-machine-driven interactive character — see §6. ⚠ Rive *editor* is free to create but **exporting .riv requires the ~$9/mo tier** (one month suffices, or use the documented SVG+Motion fallback mascot) |
| Celebrations | `canvas-confetti` | ISC | Battle-tested (GitHub itself uses it); `disableForReducedMotion: true` built in |
| UI sounds | `use-sound` (+ Howler) | MIT | ~1kB hook, lazy-loads Howler; maintenance-mode but stable; `react-sounds` (2025, ships a sound library) is the documented alternative |
| Word-count ticker | `@number-flow/react` | MIT | Dependency-free animated numbers; respects reduced-motion by default |
| Animated shadcn components | **Magic UI** (via `npx shadcn add`) | MIT (verified LICENSE.md) | Sparkles Text, Border Beam, **Animated Beam** (node-connection "ink flow" on the canvas), Animated List, Blur Fade. (Aceternity UI: free components MIT but audit per component; Pro is proprietary) |
| Beat-board drag & drop | `@dnd-kit/core` + `@dnd-kit/sortable` | MIT | Best keyboard accessibility (KeyboardSensor + screen-reader announcements) — non-negotiable for this app |
| Tailwind animations | `tw-animate-css` | MIT | shadcn's own Tailwind-v4 default; replaces deprecated `tailwindcss-animate` |
| Tab/page transitions | **View Transitions API** (native) | — | Same-document `document.startViewTransition()`; in WebView2 since Chromium 111 (evergreen WebView2 is far past this; fixed-version bundles must be ≥111). React's `<ViewTransition>` is still Canary — call the raw API |
| Cinematic one-offs | GSAP | **Free since Webflow acquisition** (incl. SplitText, MorphSVG) | For rare set-piece moments only (e.g., the "draft compiled" title-card animation) — not the everyday animation layer |

### Signature moments (where delight is spent, deliberately)

- **Canvas "ink flow"**: node connections render as quill-ink lines; Magic UI Animated Beam-style pulses run along edges when related nodes update — the Blender-nodes fantasy, on brand.
- **Word-count inkwell**: a NumberFlow ticker plus an inkwell progress ring that fills toward the daily word goal.
- **Confetti moments**: first node ever, chapter completed, draft compiled, continuity check comes back clean ("No plot holes found!"), streak milestones.
- **Sounds (Playful level)**: soft quill scribble while the AI streams, page-turn on tab switch, gentle chime on Accept. All ≤300ms, all quiet, all off in Calm.
- **Empty states**: sleeping firefly + "The night is young — jot a thought."

## 6. The mascot: the Quillnight firefly

A small firefly holding a quill, living in a corner of the app (draggable between corners, hideable entirely). Built in **Rive** (state machine, tiny .riv asset, `@rive-app/react-canvas` runtime).

**It is a status indicator first, a character second** — every state maps to real app state, so it's informative even when it's being cute:

| State | Trigger | Behavior |
|---|---|---|
| Idle | Nothing happening | Gentle hover/glow pulse |
| Thinking | LLM call in flight | Scribbles furiously on a tiny notepad; a small "via local / via Groq" provider tag appears beneath (the provider-transparency rule from [08-AI-PROVIDER-MODES.md](08-AI-PROVIDER-MODES.md), made adorable) |
| Celebrating | Enhance accepted, chapter done, milestone | Loop-de-loop + spark trail (confetti fires separately for big milestones) |
| Sleeping | App idle >5 min | Curls up; Zzz. Wakes on input |

**Asset pipeline & cost honesty**: the Rive editor is free to design in, but exporting the .riv file requires the ~$9/month tier — a one-month cost, flagged in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md). **v1.0 ships the ambient firefly** (a pure CSS/Motion glowing particle — zero asset dependency); **the full Rive companion is a v1.1 deliverable** (see [06-ROADMAP.md](06-ROADMAP.md)). If the Rive cost/tooling ever blocks, the fallback is a layered-SVG mascot animated with Motion variants — less fluid, same states.

## 7. First-run: the Reading Comfort Wizard

Personalization is the *most* evidence-backed accessibility feature (individual differences dominate every group-level finding above). So setup IS the feature, not a chore screen:

1. **Font self-test** (~60s): read the same passage in each font, tap through; the app recommends the measured-fastest and lets you override.
2. **Spacing sliders** with a live preview paragraph (letter spacing first — best evidence).
3. **Theme pick**: Day / Night / auto-by-time, plus the warm-tint slider.
4. **Delight level**: Calm / Standard / **Playful (pre-selected)** — with a live demo of what each means (one small confetti burst on selecting Playful, naturally).
5. Everything re-runnable anytime from Settings → "Reading Comfort."

## 8. Delight levels

| | Calm | Standard | Playful (default) |
|---|---|---|---|
| Motion (layout/transitions) | ✓ (subtle) | ✓ | ✓ |
| Confetti | — | Major milestones only | All milestones |
| Sounds | — | — | ✓ (quiet) |
| Mascot | Hidden | Present, quiet | Fully animated |
| Ambient firefly / particles | — | ✓ | ✓ |
| Word-ticker animation | Static number | ✓ | ✓ + inkwell ring |

`prefers-reduced-motion` overrides everything to Calm-motion behavior regardless of level. Every row above is also an individual toggle.

## 9. Gamification (gentle, writer-shaped)

- **v1.0**: writing streaks + daily word goal (from `writing_sessions`), inkwell progress ring, streak confetti. No guilt mechanics — a missed day pauses, never shames; streaks have a "freeze" day per week automatically.
- **v1.1**: achievements/badges (`achievements` table) — "First Chapter," "Plot Twist Master" (first twist node), "Night Owl" (a session past midnight — obligatory), "Continuity Clean" (10 checks, zero criticals).

## Sources

Font/individuality: [Wallace et al. 2022, TOCHI](https://dl.acm.org/doi/fullHtml/10.1145/3502222) · OpenDyslexic null results: [Wery & Diliberto 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5629233/) · Letter spacing: [Zorzi et al. 2012, PNAS](https://www.pnas.org/doi/10.1073/pnas.1205566109) · Layout: [BDA Style Guide 2023](https://cdn.bdadyslexia.org.uk/uploads/documents/Advice/style-guide/BDA-Style-Guide-2023.pdf) · Warm backgrounds: [Rello & Bigham 2017](https://dl.acm.org/doi/10.1145/3132525.3132546) · Overlays debunked: [Henderson et al. 2011](https://pubmed.ncbi.nlm.nih.gov/21930551/) · Reading rulers: [Adobe, CHI 2023](https://dl.acm.org/doi/10.1145/3544548.3581367) · Bionic Reading null: [Acta Psychologica 2024](https://www.sciencedirect.com/science/article/pii/S0001691824001811), [Readwise test](https://blog.readwise.io/bionic-reading-results/) · Atkinson Next: [Braille Institute](https://www.brailleinstitute.org/about-us/news/braille-institute-launches-enhanced-atkinson-hyperlegible-font-to-make-reading-easier/) · Word prediction: [Evmenova et al. 2010](https://journals.sagepub.com/doi/abs/10.1111/j.1540-5826.2010.00315.x) · Packages: [motion](https://motion.dev/), [auto-animate](https://auto-animate.formkit.com/), [Rive pricing](https://rive.app/pricing), [canvas-confetti](https://www.npmjs.com/package/canvas-confetti), [number-flow](https://number-flow.barvian.me/), [Magic UI license](https://github.com/magicuidesign/magicui/blob/main/LICENSE.md), [dnd-kit](https://dndkit.com/), [tw-animate-css](https://github.com/Wombosvideo/tw-animate-css), [View Transitions support](https://caniuse.com/view-transitions), [GSAP free](https://gsap.com/pricing/)

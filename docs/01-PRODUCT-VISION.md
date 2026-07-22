# Product Vision

## Core idea

A single local **Story Library** holds everything you ever create: every book, every script, every scene, every character. Nothing lives in an isolated per-project silo unless you explicitly want it to — a scene written for one book can be dragged into a completely different movie script five minutes or five years later, with zero copy/paste and zero re-typing.

## The Story Library

- The app opens directly into the Library — a list/grid of **Books**.
- A **Book** is a container with a **type**, chosen at creation:
  - **Story Book** — a novel/prose manuscript.
  - **Movie Script** — a feature-length screenplay.
  - **Short Film Script** — a shorter screenplay.
  - **Single Scene** — one standalone scene, not yet attached to a larger work.
- Book type can be **changed later** (see "Book type conversion" below) — a Single Scene can grow into a full Movie Script; a Story Book can be adapted into a Short Film Script.
- **Scenes and Codex entries (characters, locations, etc.) are canonical** — they exist independently of any one Book. Attaching a scene to a Book is a link, not a copy. Editing that scene from inside Book A immediately reflects in Book B if it's linked there too, because it is the same underlying entity.

## The three tabs (per Book)

### Tab 1 — Node Canvas

A freeform, Blender-style canvas of connected nodes (built on React Flow). This is where raw, unstructured creative thought happens.

- **Node types**: Scene, Plot Point/Twist, Thought (general idea/note).
- Every node has:
  - A **mandatory Title**.
  - An **optional Description** (free text body).
  - An **Enhance button** — sends the node's text to the local LLM to correct grammar, improve prose, and flag potential continuity issues. The result is always shown as a **diff you Accept, Reject, or further edit** — the app never silently rewrites your words.
  - The ability to **attach images** (from either image bucket, see below).
  - The ability to **link Character/Codex entries** relevant to that node.
  - **Connectors** to other nodes, so you can visually map how a plot point leads to a scene, how a twist connects to earlier setup, etc. — exactly like connecting nodes in Blender's shader/compositor editors.
- A **Characters/Codex panel** sits alongside the canvas in this tab, for quick reference and linking while you write (full Codex detail below).
- **Script-type Books (Movie Script / Short Film Script) get structured screenplay elements from the start**, not freeform prose: each node exposes dedicated fields for Scene Heading, Action, Character, Dialogue, Parenthetical, and Transition — matching how real screenwriting software works. Each of these fields is individually Enhance-able (the AI helps with grammar and sentence formation within that specific element, e.g. tightening an Action line or a piece of Dialogue), rather than writing loose prose that gets reinterpreted into screenplay structure later. This avoids the AI having to guess scene-heading/dialogue boundaries after the fact — exactly the kind of ambiguity that causes "loopholes."
- Story Book / Single Scene nodes stay freeform prose (Title + Description), enhanced the same way.

### Tab 2 — Outline / Timeline ("the mediator")

This tab is the bridge between raw node-thoughts (Tab 1) and the finished draft (Tab 3). It combines two views over the *same underlying scene-order data*:

- **Outline / Beat-board view**: drag your Tab-1 nodes into chapter/scene order. Optionally apply a **structure template** — Three-Act, Hero's Journey, or Freeform — which annotates your scenes against named story beats (e.g. "Inciting Incident," "Midpoint," "Climax").
- **Timeline / Sequencer view**: the same scenes laid out left-to-right by **in-story chronological time** rather than narrative/reveal order — useful for tracking flashbacks, parallel storylines, or any case where the order you tell the story differs from the order it happens.
- Toggling between the two views doesn't lose or duplicate data; they're two lenses on one ordering.
- **AI-assisted continuity checks** run here, using the Codex as ground truth: e.g. flagging a character referenced before their introduction, or a contradicted trait (eye color changing, a "dead" character reappearing without explanation). Flags are surfaced before you move to drafting, not discovered after the fact.

### Tab 3 — Final Draft

Compiles the ordered scenes into the finished output, formatted according to the Book's type:

- **Books**: manuscript formatting, chapter titles, preface/front-matter fields (title page, dedication, etc.), maintained per chapter.
- **Scripts**: proper scene-heading/action/character/dialogue formatting, industry-standard layout.
- This tab is also where you trigger export (see [05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md)) and where **draft versions/snapshots** are kept, so past compiled drafts aren't lost when you compile a new one.

## The Codex (character & world tracking)

A full structured system, in the spirit of NovelCrafter's "Codex" — not just free-text notes:

- **Entity types**: Characters, Locations, Factions/Groups, Objects/Lore.
- Each entry has **custom fields** (e.g. for a Character: traits, relationships, arc/status-over-time), an optional image, and can be **cross-linked** to other entries (a Character belongs to a Faction, a Location is owned by a Character, etc.).
- Entries track **point-in-time state** — so if a character's status or a key trait changes partway through the story, the Codex knows what was true *at that point*, and the AI won't "spoil" a later development into an earlier scene's Enhance call.
- Codex entries are **automatically injected into the LLM's context** during Enhance and continuity-check calls, which is what makes the contradiction-catching actually work rather than relying on the model's own limited memory of your story.
- Like scenes, Codex entries are canonical/shared — a character can appear in as many Books as you like without duplication.

## Images

Two distinct buckets, both part of the permanent personal archive:

1. **Finalized scene images** — standard-ratio images tied to actual, finished scenes (the "this is what the scene looks like" collection).
2. **Global reference/resource pool** — a shared library of reference images across your *entire* Story Library (moodboards, inspiration, texture references, character likenesses you haven't committed to yet), searchable and taggable, usable from any Book.

Both buckets support:
- **Rename at upload time**, and **edit afterward** (name, tags).
- A **free-text description** — why you kept this image, what to take/use from it — which is itself Enhance-able by the LLM like any other text field.
- When a Book is exported as a portable bundle, **only images actually linked to that Book** are included — your whole reference pool doesn't get dragged along into every export.

## Book type conversion

Converting a Book's type (e.g. Single Scene → Movie Script, or Story Book → Short Film Script) is:

- **AI-assisted**: triggers an Enhance-style transformation pass that rewrites prose into screenplay elements (or vice versa) using the local model.
- **Human-in-the-loop**: the transformation is shown for Accept/Reject/Edit review — identical to every other Enhance call — never applied silently.
- **Non-destructive**: the original content is never overwritten. A scene keeps both its original prose (`description`) and any newly generated structured screenplay elements side by side. Converting back later, or simply preferring the original, always remains possible because nothing was deleted.

## Auto-suggest (background AI)

- **Off by default.** The LLM only runs when you explicitly click an Enhance button.
- A **settings toggle** enables background auto-suggest, which triggers on tab-switch or when you leave/blur a node — shown as a subtle inline suggestion you can accept or ignore, not an automatic overwrite.
- Regardless of the default, the underlying engineering always includes:
  - **Debounce** — waits for roughly 2.5 seconds of idle time before firing, so rapid node-hopping while brainstorming doesn't queue up a dozen requests.
  - **Auto-cancel** — aborts any in-flight generation the instant you navigate away from the node/field that triggered it.
  - **Keep-warm** — the model stays loaded between calls so there's no multi-second reload penalty each time.
- This means turning auto-suggest on later costs nothing extra to build — it's designed in from the start, just switched off by default given the hardware/performance tradeoffs discussed in [07-RISKS-AND-OPEN-QUESTIONS.md](07-RISKS-AND-OPEN-QUESTIONS.md).

## Voice input (dictation) — core feature

Speak a raw thought instead of typing it: hold the push-to-talk hotkey (or tap the mic on any text field), talk, release — the transcript lands at your cursor, and one tap of Enhance cleans the grammar. For a dyslexic writer this is often the single biggest friction-remover: ideas arrive at speaking speed, the AI handles the spelling. Transcription is local by default (cloud-boosted in Online/Hybrid mode), the raw audio is always kept alongside the transcript (never-lose-data applies to your voice too), and in a later iteration **brain-dump mode** turns a long spoken ramble into multiple draft nodes for review. Full design: [12-VOICE-AND-SPEECH.md](12-VOICE-AND-SPEECH.md).

## How it feels: Day/Night, the firefly, and joy on purpose

The full design system lives in [10-DESIGN-SYSTEM.md](10-DESIGN-SYSTEM.md); the product-level commitments:

- **Two themes named by the app itself**: ☀ **Day** — a warm cream "paper studio" tuned for long reading comfort; 🌙 **Night** — the cinematic dark studio, fireflies included. Switch manually or auto by time of day.
- **The Quillnight firefly** — a small animated companion holding a quill. It's a status indicator first (scribbles while the AI thinks — with the provider tag beneath it — celebrates when you accept, sleeps when you're idle) and a character second. Fully hideable. The ambient version ships in v1.0; the fully animated companion arrives in v1.1.
- **A first-run Reading Comfort Wizard** instead of a settings chore: a 60-second font self-test (research says measured fit beats any universal "dyslexia font"), live spacing sliders, theme choice, and a Delight level — **Calm / Standard / Playful (default: Playful)**.
- **Celebrations that earn their confetti**: first node, finished chapter, compiled draft, a continuity check that comes back clean. Soft optional UI sounds (quill scribble, page turn). An animated word-count ticker with an inkwell that fills toward your daily goal, plus writing streaks (with a built-in weekly grace day — encouragement, never guilt). Badges arrive in v1.1.
- **One hard rule holds it all together**: *playfulness lives in the chrome, never inside the manuscript.* Your actual text is always rendered in the calm, evidence-tuned reading environment — and everything animated respects reduced-motion preferences.

## Trust & data integrity principles (cross-cutting)

These apply everywhere in the app, not just to one feature:

- **Never silently overwrite.** Every AI action is a proposal you review, not an automatic edit.
- **Never lose data.** Nothing is deleted as a side effect of conversion, enhancement, or reorganization — see [05-EXPORT-IMPORT-SECURITY.md](05-EXPORT-IMPORT-SECURITY.md) for backup/export mechanics that reinforce this at the storage layer. This extends to dictation audio (kept, re-transcribable) and to every AI transformation.
- **Everything reusable.** Scenes, characters, and images are canonical entities usable across every Book you ever create — the app is meant to be a permanent personal archive, not a series of disposable one-off projects.
- **Always visible provenance.** Every AI result — enhancement, continuity flag, transcription — shows which engine produced it (local or cloud) and, for continuity flags, quotes the exact text it's flagging.

/**
 * Centralized narrative-vocabulary module (docs/06-ROADMAP.md Phase 3 task FE-5).
 *
 * Purpose: a single source of truth for the guided dropdown/select option lists
 * used by Codex entity editors (and, later, story-level generation controls),
 * so labels/values stay consistent everywhere they're rendered or stored.
 *
 * Vocabulary/naming (relationship types, character roles, trait palette, etc.)
 * sourced from the author's own VIBE repo (github.com/KarthikeyaSuppa/VIBE),
 * which the user solely owns and has authorized reusing directly (selectively
 * adapted, not a wholesale clone); the idea of "which words belong in this list"
 * was referenced.
 *
 * Two sections below:
 *  1. WIRED IN PHASE 3 — Codex-scoped vocab, actively used by Codex entity
 *     editors (characters, locations, factions, object/lore) in this phase.
 *  2. DEFINED NOW, WIRED IN PHASE 4 — story-level generation-control vocab
 *     (genre/tone/pacing/focus). Defined here so the shape is settled early,
 *     but not imported by any Phase 3 UI yet.
 *
 * Values are stable, DB-friendly snake_case/lowercase. Labels are human
 * Title Case for display. `hint` is an optional short phrase for tooltips
 * or helper text.
 */

export interface VocabOption {
  value: string
  label: string
  hint?: string
}

/** Returns the matching option's label, or the raw value if no match is found. */
export function labelFor(options: VocabOption[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value
}

// ── Codex vocab — WIRED IN PHASE 3 (Codex entity editors) ──────────────────

/** Relationship types between two Codex entries (typically characters). */
export const RELATIONSHIP_TYPES: VocabOption[] = [
  { value: 'ally', label: 'Ally', hint: 'Works together, mutual trust' },
  { value: 'rival', label: 'Rival', hint: 'Competing goals, not outright hostile' },
  { value: 'enemy', label: 'Enemy', hint: 'Actively opposed' },
  { value: 'family', label: 'Family', hint: 'Blood or adoptive kin, unspecified' },
  { value: 'parent', label: 'Parent' },
  { value: 'child', label: 'Child' },
  { value: 'sibling', label: 'Sibling' },
  { value: 'mentor', label: 'Mentor', hint: 'Teaches or guides' },
  { value: 'protege', label: 'Protégé', hint: 'Taught or guided by the other' },
  { value: 'friend', label: 'Friend' },
  { value: 'romantic', label: 'Romantic', hint: 'Romantic or intimate bond' },
  { value: 'colleague', label: 'Colleague', hint: 'Peers, shared occupation' },
  { value: 'master', label: 'Master', hint: 'Commands or owns the other' },
  { value: 'servant', label: 'Servant', hint: 'Serves or is bound to the other' },
  { value: 'creator', label: 'Creator', hint: 'Made or brought the other into being' },
  { value: 'creation', label: 'Creation', hint: 'Was made by the other' },
]

/** Narrative role a character plays in the story. */
export const CHARACTER_ROLES: VocabOption[] = [
  { value: 'protagonist', label: 'Protagonist', hint: 'Drives the main story' },
  { value: 'antagonist', label: 'Antagonist', hint: 'Opposes the protagonist' },
  { value: 'deuteragonist', label: 'Deuteragonist', hint: 'Secondary lead' },
  { value: 'foil', label: 'Foil', hint: 'Contrasts another character to sharpen them' },
  { value: 'love_interest', label: 'Love Interest' },
  { value: 'mentor', label: 'Mentor', hint: 'Guides the protagonist' },
  { value: 'sidekick', label: 'Sidekick', hint: 'Loyal companion to a lead' },
  { value: 'comic_relief', label: 'Comic Relief', hint: 'Lightens tone' },
  { value: 'supporting', label: 'Supporting', hint: 'Recurring but not central' },
  { value: 'background', label: 'Background', hint: 'Minor, mostly scenery' },
]

/** Multi-select trait tags for describing a character. */
export const CHARACTER_TRAITS: VocabOption[] = [
  { value: 'brave', label: 'Brave' },
  { value: 'cowardly', label: 'Cowardly' },
  { value: 'loyal', label: 'Loyal' },
  { value: 'cunning', label: 'Cunning' },
  { value: 'honest', label: 'Honest' },
  { value: 'ambitious', label: 'Ambitious' },
  { value: 'kind', label: 'Kind' },
  { value: 'ruthless', label: 'Ruthless' },
  { value: 'curious', label: 'Curious' },
  { value: 'stoic', label: 'Stoic' },
  { value: 'impulsive', label: 'Impulsive' },
  { value: 'cautious', label: 'Cautious' },
  { value: 'charismatic', label: 'Charismatic' },
  { value: 'reclusive', label: 'Reclusive' },
  { value: 'optimistic', label: 'Optimistic' },
  { value: 'cynical', label: 'Cynical' },
  { value: 'disciplined', label: 'Disciplined' },
  { value: 'reckless', label: 'Reckless' },
  { value: 'compassionate', label: 'Compassionate' },
  { value: 'vengeful', label: 'Vengeful' },
  { value: 'humble', label: 'Humble' },
  { value: 'arrogant', label: 'Arrogant' },
  { value: 'patient', label: 'Patient' },
  { value: 'hot_tempered', label: 'Hot-Tempered' },
  { value: 'resourceful', label: 'Resourceful' },
  { value: 'naive', label: 'Naive' },
  { value: 'wise', label: 'Wise' },
  { value: 'secretive', label: 'Secretive' },
]

/** Kind of place for a location Codex entry. */
export const LOCATION_KINDS: VocabOption[] = [
  { value: 'city', label: 'City' },
  { value: 'village', label: 'Village' },
  { value: 'castle', label: 'Castle' },
  { value: 'wilderness', label: 'Wilderness' },
  { value: 'dungeon', label: 'Dungeon' },
  { value: 'building', label: 'Building' },
  { value: 'region', label: 'Region' },
  { value: 'realm', label: 'Realm' },
  { value: 'landmark', label: 'Landmark' },
  { value: 'vessel', label: 'Vessel', hint: 'Ship, airship, or other mobile place' },
  { value: 'other', label: 'Other' },
]

/** Kind of organization for a faction Codex entry. */
export const FACTION_KINDS: VocabOption[] = [
  { value: 'guild', label: 'Guild' },
  { value: 'kingdom', label: 'Kingdom' },
  { value: 'cult', label: 'Cult' },
  { value: 'company', label: 'Company' },
  { value: 'tribe', label: 'Tribe' },
  { value: 'order', label: 'Order' },
  { value: 'rebellion', label: 'Rebellion' },
  { value: 'government', label: 'Government' },
  { value: 'family_house', label: 'Family House' },
  { value: 'criminal', label: 'Criminal', hint: 'Gang, syndicate, or similar' },
  { value: 'other', label: 'Other' },
]

/** Kind of item for an object/lore Codex entry (entry_type 'object_lore'). */
export const OBJECT_KINDS: VocabOption[] = [
  { value: 'weapon', label: 'Weapon' },
  { value: 'artifact', label: 'Artifact' },
  { value: 'tool', label: 'Tool' },
  { value: 'document', label: 'Document' },
  { value: 'treasure', label: 'Treasure' },
  { value: 'vehicle', label: 'Vehicle' },
  { value: 'substance', label: 'Substance' },
  { value: 'relic', label: 'Relic' },
  { value: 'other', label: 'Other' },
]

// ── Story-level vocab — DEFINED for Phase 4 (Outline/Continuity); NOT wired to any UI in Phase 3 ──

/** Overall genre for the story. */
export const GENRES: VocabOption[] = [
  { value: 'fantasy', label: 'Fantasy' },
  { value: 'science_fiction', label: 'Science Fiction' },
  { value: 'mystery', label: 'Mystery' },
  { value: 'thriller', label: 'Thriller' },
  { value: 'romance', label: 'Romance' },
  { value: 'horror', label: 'Horror' },
  { value: 'historical', label: 'Historical' },
  { value: 'literary', label: 'Literary' },
  { value: 'adventure', label: 'Adventure' },
  { value: 'comedy', label: 'Comedy' },
  { value: 'drama', label: 'Drama' },
  { value: 'young_adult', label: 'Young Adult' },
  { value: 'dystopian', label: 'Dystopian' },
  { value: 'fairy_tale', label: 'Fairy Tale' },
]

/** Overall tone the story should carry. */
export const TONES: VocabOption[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'lighthearted', label: 'Lighthearted' },
  { value: 'serious', label: 'Serious' },
  { value: 'whimsical', label: 'Whimsical' },
  { value: 'gritty', label: 'Gritty' },
  { value: 'hopeful', label: 'Hopeful' },
  { value: 'melancholic', label: 'Melancholic' },
  { value: 'satirical', label: 'Satirical' },
  { value: 'epic', label: 'Epic' },
  { value: 'intimate', label: 'Intimate' },
  { value: 'suspenseful', label: 'Suspenseful' },
  { value: 'comedic', label: 'Comedic' },
]

/** How quickly the story should move. */
export const PACING: VocabOption[] = [
  { value: 'slow_burn', label: 'Slow Burn', hint: 'Deliberate, lingers on detail' },
  { value: 'steady', label: 'Steady', hint: 'Even, measured tempo' },
  { value: 'brisk', label: 'Brisk', hint: 'Moves along without dawdling' },
  { value: 'fast', label: 'Fast', hint: 'Quick scene turnover' },
  { value: 'breakneck', label: 'Breakneck', hint: 'Relentless, page-turner speed' },
]

/** How many point-of-view characters the story tracks. */
export const CHARACTER_FOCUS: VocabOption[] = [
  { value: 'single_protagonist', label: 'Single Protagonist', hint: 'One POV throughout' },
  { value: 'dual_leads', label: 'Dual Leads', hint: 'Two alternating POVs' },
  { value: 'ensemble', label: 'Ensemble', hint: 'A group shares the spotlight' },
  { value: 'multi_pov', label: 'Multi-POV', hint: 'Several rotating POVs' },
]

/**
 * Preset avatar set for local profiles (docs/0X auth). Deliberately just an emoji id —
 * no upload/crop flow needed for a 1-2 profile local picker.
 */
export interface AvatarOption {
  id: string
  label: string
  emoji: string
}

export const AVATAR_OPTIONS: AvatarOption[] = [
  { id: 'fox', label: 'Fox', emoji: '🦊' },
  { id: 'owl', label: 'Owl', emoji: '🦉' },
  { id: 'cat', label: 'Cat', emoji: '🐈' },
  { id: 'moon', label: 'Moon', emoji: '🌙' },
  { id: 'star', label: 'Star', emoji: '⭐' },
  { id: 'quill', label: 'Quill', emoji: '🪶' },
  { id: 'book', label: 'Book', emoji: '📖' },
  { id: 'ink', label: 'Ink', emoji: '🖋️' },
]

const DEFAULT_AVATAR = AVATAR_OPTIONS[0]

/** Resolves a stored avatar id (or a legacy/unknown value) to a displayable option. */
export function resolveAvatar(avatarId: string | null | undefined): AvatarOption {
  return AVATAR_OPTIONS.find((a) => a.id === avatarId) ?? DEFAULT_AVATAR
}

/** Renders an avatar's emoji as a plain string — callers wrap it in whatever chrome they need. */
export function avatarEmoji(avatarId: string | null | undefined): string {
  return resolveAvatar(avatarId).emoji
}

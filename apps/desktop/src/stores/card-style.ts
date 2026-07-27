import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Canvas node-card shape preference (docs/10 node canvas redesign). Persisted to
 * localStorage via zustand's `persist` middleware, following `quillnight-<name>` naming
 * (see `theme.ts`'s `quillnight-theme` key). Defaults to `'rectangle'` so existing users
 * with no stored preference see today's look unchanged.
 */

export type CardStyle = 'rectangle' | 'square'

interface CardStyleState {
  cardStyle: CardStyle
  setCardStyle: (style: CardStyle) => void
}

export const useCardStyleStore = create<CardStyleState>()(
  persist(
    (set) => ({
      cardStyle: 'rectangle',
      setCardStyle: (cardStyle) => set({ cardStyle }),
    }),
    { name: 'quillnight-card-style' },
  ),
)

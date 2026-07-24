import { create } from 'zustand'
import type { NodeType } from '@/lib/api'

/**
 * A thin bridge between `CanvasPanelInner` (mounted inside a `ReactFlowProvider`, deep in
 * the Canvas tab's content) and the book-screen tab row (a sibling, outside that provider).
 * `handleAddNode` in `canvas-panel.tsx` doesn't need React Flow's viewport/context — it only
 * needs the current node count (for placement stagger) and the `createNode` mutation — but
 * both of those live in `CanvasPanelInner`'s local state, so the handler itself has to stay
 * there. The canvas registers its current handler here on mount/update; the tab row reads it
 * and calls it, without either side importing the other.
 */
interface CanvasActionsState {
  addNode: ((nodeType: NodeType) => void) | null
  addNodePending: boolean
  setAddNode: (addNode: ((nodeType: NodeType) => void) | null, pending: boolean) => void
}

export const useCanvasActionsStore = create<CanvasActionsState>((set) => ({
  addNode: null,
  addNodePending: false,
  setAddNode: (addNode, pending) => set({ addNode, addNodePending: pending }),
}))

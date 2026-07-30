import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeTypes,
  type NodeMouseHandler,
  type OnConnect,
  type OnEdgesDelete,
  type OnNodeDrag,
  type OnNodesDelete,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import NumberFlow from '@number-flow/react'
import {
  Compass,
  LayoutGrid,
  LayoutTemplate,
  Lightbulb,
  Maximize,
  MapPinned,
  Minimize2,
  Sparkles,
} from 'lucide-react'
import { useCanvasActionsStore } from '@/stores/canvas-actions'
import {
  useCanvas,
  useCreateEdge,
  useCreateNode,
  useDeleteEdge,
  useRemoveFromCanvas,
  useUpdateNodePosition,
} from '@/queries/canvas'
import { useApplyCanvasTemplate, type CanvasTemplateKey } from '@/queries/canvas-templates'
import { useBook } from '@/queries/books'
import type { CanvasNode as CanvasNodeDto, NodeType } from '@/lib/api'
import { nodeTypes, type CanvasNodeData, type SceneFlowNode } from '@/components/canvas/nodes'
import { NodeEditor } from '@/components/canvas/node-editor'
import { CodexPanel } from '@/components/canvas/codex-panel'
import { InkEdge } from '@/components/canvas/ink-edge'
import { Firefly } from '@/components/firefly'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useThemeStore } from '@/stores/theme'
import { useDelight, isFirstNodeMilestone } from '@/lib/delight'
import { LottiePlayer } from '@/lib/lottie'
import { cn } from '@/lib/utils'

/** All edges render as the quill-ink styled edge (docs/10 §5, `InkEdge`) — its animated
 * flow layer is itself gated on `useDelight().motionOk`, so registering it here doesn't
 * bypass the calm/reduced-motion gating. */
const edgeTypes: EdgeTypes = { ink: InkEdge }

const DEFAULT_TITLES: Record<NodeType, string> = {
  scene: 'Untitled scene',
  plot_point: 'Untitled plot point',
  thought: 'Untitled thought',
}

export const NODE_MENU: { nodeType: NodeType; label: string; icon: typeof Sparkles }[] = [
  { nodeType: 'scene', label: 'Scene', icon: LayoutGrid },
  { nodeType: 'plot_point', label: 'Plot Point', icon: MapPinned },
  { nodeType: 'thought', label: 'Thought', icon: Lightbulb },
]

/** The empty-canvas "start from a template" entry point (docs/06 Phase 9 task 5). Keys must
 * match `app/services/canvas_template_service.py`'s `CANVAS_TEMPLATES`/`TEMPLATE_LABELS`. */
const CANVAS_TEMPLATE_MENU: { key: CanvasTemplateKey; label: string; icon: typeof Sparkles }[] = [
  { key: 'three_act', label: 'Three-Act Structure', icon: LayoutTemplate },
  { key: 'heros_journey', label: "Hero's Journey", icon: Compass },
]

/** On script-type Books, "scene" nodes render as the structured `screenplay` variant
 * (docs/06 Phase 2 task G4); plot_point/thought nodes are unchanged. The canonical
 * server-side node_type is untouched — this is a display-only remap. */
function toFlowNode(node: CanvasNodeDto, isScriptBook: boolean, bookId: string): SceneFlowNode {
  const displayType = isScriptBook && node.node_type === 'scene' ? 'screenplay' : node.node_type
  return {
    id: node.scene_id,
    type: displayType,
    position: { x: node.canvas_x ?? 0, y: node.canvas_y ?? 0 },
    // xyflow's own node wrapper is what actually carries keyboard focus (it's natively
    // tabIndex=0/focusable — see the keyboard-audit note on `handleCanvasKeyDown` below), so
    // the app's standard focus-ring token (same one `button.tsx`/`input.tsx` use) is applied
    // here via `className` rather than invented fresh for the canvas.
    className: 'rounded-2xl outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50',
    // TODO(FE-B): CanvasNodeData in nodes.tsx needs bookId/nodeType fields — added in the paired task
    data: {
      linkId: node.link_id,
      sceneId: node.scene_id,
      bookId,
      nodeType: node.node_type,
      title: node.title,
      description: node.description,
      status: node.status,
    },
  }
}

/** A small keyed debounce — coalesces rapid calls for the same key (a dragged node id). */
function useDebouncedByKey<Args extends unknown[]>(fn: (...args: Args) => void, delayMs: number) {
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  useEffect(() => {
    const map = timers.current
    return () => {
      map.forEach((timer) => clearTimeout(timer))
      map.clear()
    }
  }, [])

  return useCallback(
    (key: string, ...args: Args) => {
      const existing = timers.current.get(key)
      if (existing) clearTimeout(existing)
      timers.current.set(
        key,
        setTimeout(() => {
          timers.current.delete(key)
          fn(...args)
        }, delayMs),
      )
    },
    [fn, delayMs],
  )
}

/** The Node Canvas (docs/01 §Node Canvas, docs/06 Phase 2 tasks G1-G3). Nested in a
 * ReactFlowProvider so future toolbars/panels can reach `useReactFlow()` if needed. */
export function CanvasPanel({ bookId }: { bookId: string }) {
  return (
    <ReactFlowProvider>
      <CanvasPanelInner bookId={bookId} />
    </ReactFlowProvider>
  )
}

function CanvasPanelInner({ bookId }: { bookId: string }) {
  const { data: canvas, isLoading } = useCanvas(bookId)
  const { data: book } = useBook(bookId)
  const isScriptBook = book?.book_type === 'movie_script' || book?.book_type === 'short_film_script'
  const createNode = useCreateNode(bookId)
  const updatePosition = useUpdateNodePosition(bookId)
  const removeFromCanvas = useRemoveFromCanvas(bookId)
  const createEdge = useCreateEdge(bookId)
  const deleteEdge = useDeleteEdge(bookId)
  const applyTemplate = useApplyCanvasTemplate(bookId)

  const [nodes, setNodes, onNodesChange] = useNodesState<SceneFlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const { fitView } = useReactFlow()

  // Keyboard-first node creation (docs/06 Phase 9 task 6, docs/14 §B "Keyboard-first node
  // creation"). Set by `handleAddNodeWithFocus` once the create mutation resolves with the
  // new node's id; the effect further below moves DOM focus to it as soon as it's actually
  // present in `nodes` (the canvas query has to refetch and re-render first).
  const [pendingFocusNodeId, setPendingFocusNodeId] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Keyboard-driven edge creation (docs/06 Phase 9 task 7 — "the genuine missing a11y
  // capability", docs/14 §B). `connectSourceId` is the node id connect-mode was started from;
  // non-null means connect-mode is active. `connectAnnouncement` feeds the aria-live region
  // below so a sighted-or-not keyboard user gets the same state changes a mouse user sees
  // implicitly (a dragged connection line).
  const [connectSourceId, setConnectSourceId] = useState<string | null>(null)
  const [connectAnnouncement, setConnectAnnouncement] = useState('')

  // The server is the source of truth; local drag state is reconciled back into it once
  // a mutation settles and the canvas query refetches (never the other way around).
  useEffect(() => {
    if (!canvas) return
    setNodes(canvas.nodes.map((node) => toFlowNode(node, isScriptBook, bookId)))
    setEdges(
      canvas.edges.map((edge) => ({
        id: edge.id,
        source: edge.source_scene_id,
        target: edge.target_scene_id,
        sourceHandle: edge.source_handle ?? undefined,
        targetHandle: edge.target_handle ?? undefined,
        label: edge.label ?? undefined,
        type: 'ink',
        data: { connectionType: edge.connection_type },
      })),
    )
  }, [canvas, isScriptBook, bookId, setNodes, setEdges])

  const debouncedSavePosition = useDebouncedByKey<[string, number, number]>(
    (sceneId, canvas_x, canvas_y) => updatePosition.mutate({ sceneId, canvas_x, canvas_y }),
    350,
  )

  const handleNodeDragStop: OnNodeDrag<SceneFlowNode> = useCallback(
    (_event, node) => {
      debouncedSavePosition(node.id, node.data.sceneId, node.position.x, node.position.y)
    },
    [debouncedSavePosition],
  )

  const handleConnect: OnConnect = useCallback(
    (connection: Connection) => {
      createEdge.mutate({
        source_scene_id: connection.source,
        target_scene_id: connection.target,
        source_handle: connection.sourceHandle,
        target_handle: connection.targetHandle,
      })
    },
    [createEdge],
  )

  const handleEdgesDelete: OnEdgesDelete = useCallback(
    (removed) => {
      removed.forEach((edge) => deleteEdge.mutate(edge.id))
    },
    [deleteEdge],
  )

  const handleNodesDelete: OnNodesDelete<SceneFlowNode> = useCallback(
    (removed) => {
      removed.forEach((node) => removeFromCanvas.mutate(node.data.sceneId))
      setSelectedNodeId((current) => (removed.some((node) => node.id === current) ? null : current))
    },
    [removeFromCanvas],
  )

  const handleNodeClick: NodeMouseHandler<SceneFlowNode> = useCallback((_event, node) => {
    setSelectedNodeId(node.id)
  }, [])

  // A node's display title, for the connect-mode aria-live announcements below.
  const nodeTitleById = useCallback(
    (nodeId: string) => nodes.find((node) => node.id === nodeId)?.data.title ?? 'node',
    [nodes],
  )

  // Confirms a keyboard-driven connection (docs/06 Phase 9 task 7): creates an edge through
  // the exact same mutation the mouse drag-to-connect flow uses (`handleConnect` above), since
  // a flow node's `id` is already the canonical `scene_id` (see `toFlowNode`). A same-node
  // "confirm" (nothing was Tabbed to in between) is a no-op — connect-mode stays active rather
  // than silently failing or creating a self-edge.
  const confirmConnection = useCallback(
    (targetNodeId: string | null) => {
      if (!connectSourceId || !targetNodeId || targetNodeId === connectSourceId) return
      createEdge.mutate({ source_scene_id: connectSourceId, target_scene_id: targetNodeId })
      setConnectAnnouncement(
        `Connected ${nodeTitleById(connectSourceId)} to ${nodeTitleById(targetNodeId)}.`,
      )
      setConnectSourceId(null)
    },
    [connectSourceId, createEdge, nodeTitleById],
  )

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  )

  const theme = useThemeStore((s) => s.theme)
  const { level: delightLevel, motionOk, fireConfetti, fireDelightAccent } = useDelight()

  const nodeCount = nodes.length
  const handleAddNode = useCallback(
    (nodeType: NodeType) => {
      const stagger = nodeCount * 32
      createNode.mutate({
        node_type: nodeType,
        title: DEFAULT_TITLES[nodeType],
        canvas_x: 80 + stagger,
        canvas_y: 80 + stagger,
      })
      // The very first node created anywhere in the app, ever — a one-time milestone
      // (docs/10 §5). `isFirstNodeMilestone()` flips the localStorage flag and returns
      // true only on that first call, so this never fires again after. `fireDelightAccent`
      // layers the one-shot Lottie accent on top of confetti at Playful only — Standard
      // stays confetti-only (it no-ops itself if not 'playful').
      if (isFirstNodeMilestone()) {
        fireConfetti({ major: true })
        fireDelightAccent()
      }
    },
    [createNode, nodeCount, fireConfetti, fireDelightAccent],
  )

  // Keyboard-first node creation (docs/06 Phase 9 task 6): same create call as `handleAddNode`
  // (always a "scene" — the keyboard shortcut has no menu to pick a node type from, mirroring
  // how `Shift+N` in other apps means "the default new thing"), but additionally captures the
  // created node's id from the mutation's own `onSuccess` so the effect below can move DOM
  // focus to it once it's actually rendered.
  const handleAddNodeWithFocus = useCallback(() => {
    const nodeType: NodeType = 'scene'
    const stagger = nodeCount * 32
    createNode.mutate(
      {
        node_type: nodeType,
        title: DEFAULT_TITLES[nodeType],
        canvas_x: 80 + stagger,
        canvas_y: 80 + stagger,
      },
      { onSuccess: (canvasNode) => setPendingFocusNodeId(canvasNode.scene_id) },
    )
    if (isFirstNodeMilestone()) {
      fireConfetti({ major: true })
      fireDelightAccent()
    }
  }, [createNode, nodeCount, fireConfetti, fireDelightAccent])

  // Once the newly-created node id shows up in `nodes` (the canvas query has refetched and
  // xyflow has rendered its wrapper), move DOM focus onto it. `requestAnimationFrame` gives the
  // just-committed DOM a paint before querying for it — the same caution `isFullscreen`'s
  // `fitView` effect above takes with a short `setTimeout` after its own layout-affecting change.
  useEffect(() => {
    if (!pendingFocusNodeId) return
    if (!nodes.some((node) => node.id === pendingFocusNodeId)) return
    const raf = requestAnimationFrame(() => {
      containerRef.current
        ?.querySelector<HTMLElement>(`[data-id="${pendingFocusNodeId}"]`)
        ?.focus()
    })
    setPendingFocusNodeId(null)
    return () => cancelAnimationFrame(raf)
  }, [pendingFocusNodeId, nodes])

  // Keyboard audit fix (Phase 8): every node is already natively Tab-focusable (@xyflow/react
  // gives its `.react-flow__node` wrapper `tabIndex=0` by default — `nodesFocusable` is on
  // unless explicitly disabled, which this canvas never does). But xyflow's *own* internal
  // Enter/Space keydown handling only toggles its internal selection state — it never calls
  // the `onNodeClick` prop, so Enter previously did nothing visible (no drawer opened).
  // This listens on the canvas container (an ancestor of every node wrapper, so the keydown
  // bubbles up to it) and opens the same `NodeEditor` a mouse click would, but only when the
  // keydown's target is the node wrapper itself — not a descendant like the Duplicate/⋯
  // buttons rendered inside the card, which already handle their own Enter natively.
  //
  // Phase 9 tasks 6+7 extend this same handler with two more bindings. Both use `Shift+<letter>`
  // specifically because it collides with nothing already active on this canvas: xyflow's own
  // defaults here are Backspace/Delete (`deleteKeyCode` above), arrow keys (built-in node nudge),
  // and `Shift` held while *dragging the pane* (its default `selectionKeyCode`, mouse-only — a
  // bare `Shift+<letter>` keypress never starts a drag); the app's global `R`/`F` reading
  // shortcuts (`lib/reading-shortcuts.ts`) are single letters with no modifier and are only ever
  // mounted on the manuscript reader route, not here.
  //   - `Shift+N` — task 6: add a node and move focus straight to it.
  //   - `Shift+C` — task 7: start connect-mode from the focused node; pressed again (or Enter)
  //     confirms a connection to whichever node is now focused. `Escape` cancels.
  const handleCanvasKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement
      const isNodeTarget = target.classList?.contains('react-flow__node')
      const targetNodeId = isNodeTarget ? target.getAttribute('data-id') : null
      const hasModifier = event.ctrlKey || event.altKey || event.metaKey

      if (!hasModifier && event.shiftKey && event.key.toLowerCase() === 'n') {
        event.preventDefault()
        handleAddNodeWithFocus()
        return
      }

      if (!hasModifier && event.shiftKey && event.key.toLowerCase() === 'c') {
        event.preventDefault()
        if (!connectSourceId) {
          if (!targetNodeId) return
          setConnectSourceId(targetNodeId)
          setConnectAnnouncement(
            `Connecting from ${nodeTitleById(targetNodeId)}. Tab to a target node and press Enter.`,
          )
        } else {
          confirmConnection(targetNodeId)
        }
        return
      }

      if (connectSourceId && event.key === 'Escape') {
        event.preventDefault()
        setConnectSourceId(null)
        setConnectAnnouncement('Connection cancelled.')
        return
      }

      if (event.key === 'Enter') {
        if (connectSourceId) {
          event.preventDefault()
          confirmConnection(targetNodeId)
          return
        }
        if (!isNodeTarget || !targetNodeId) return
        event.preventDefault()
        setSelectedNodeId(targetNodeId)
      }
    },
    [connectSourceId, confirmConnection, nodeTitleById, handleAddNodeWithFocus],
  )

  // Bridges `handleAddNode` out to the book-screen tab row, which renders the "Add node"
  // control on the tab bar (docs/06 Phase 2) but sits outside this component (and outside
  // the ReactFlowProvider). Cleared on unmount so a stale handler is never left registered.
  //
  // `handleAddNode` gets a fresh identity every render (it closes over `nodeCount` etc.), so
  // registering it directly as the store's `addNode` would re-write the store — and thus
  // re-render `BookScreen`, which re-renders this component's whole subtree — on every render,
  // forever (React's nested-update-depth guard eventually throws "Maximum update depth
  // exceeded"). Instead we register one function whose *identity* never changes for the
  // lifetime of this component, and have it delegate through a ref to whatever the latest
  // `handleAddNode` is. The store write (and the resulting `BookScreen` re-render) then only
  // happens once, on mount/unmount, instead of every render.
  const handleAddNodeRef = useRef(handleAddNode)
  useEffect(() => {
    handleAddNodeRef.current = handleAddNode
  }, [handleAddNode])

  const stableAddNode = useRef((nodeType: NodeType) => handleAddNodeRef.current(nodeType)).current

  const setAddNode = useCanvasActionsStore((s) => s.setAddNode)
  useEffect(() => {
    setAddNode(stableAddNode, false)
    return () => setAddNode(null, false)
  }, [setAddNode, stableAddNode])

  // `addNodePending` is a plain boolean — updating it doesn't need to touch the `addNode`
  // function identity at all, so it gets its own effect keyed only on the primitive pending
  // flag (bounded churn: it only fires when the mutation's pending state actually flips).
  const isPending = createNode.isPending
  useEffect(() => {
    setAddNode(stableAddNode, isPending)
  }, [setAddNode, stableAddNode, isPending])

  const handleApplyTemplate = useCallback(
    (templateKey: CanvasTemplateKey) => {
      applyTemplate.mutate({ template_key: templateKey })
    },
    [applyTemplate],
  )

  const isEmpty = useMemo(() => !isLoading && nodes.length === 0, [isLoading, nodes.length])

  // Visible connect-mode indicator (docs/06 Phase 9 task 7): a render-time-only className
  // overlay on the connect-mode source node — never written back into `nodes`/`setNodes`, so
  // it can't fight the drag/position-save flow or leak into the mutation payloads above. Falls
  // back to the plain `nodes` array (skipping the `.map`) whenever connect-mode isn't active.
  const displayNodes = useMemo(() => {
    if (!connectSourceId) return nodes
    return nodes.map((node) =>
      node.id === connectSourceId
        ? { ...node, className: cn(node.className, 'ring-4 ring-primary ring-offset-2 ring-offset-background') }
        : node,
    )
  }, [nodes, connectSourceId])

  // Total words across the canvas's scenes (docs/10 §5 word ticker): sums each node's
  // `word_count` if the canvas DTO ever carries it, otherwise falls back to a plain node
  // count so the ticker still means something today.
  const totalWords = useMemo(() => {
    let sum = 0
    let hasWordCounts = false
    for (const node of nodes) {
      const wordCount = (node.data as CanvasNodeData & { word_count?: unknown }).word_count
      if (typeof wordCount === 'number') {
        hasWordCounts = true
        sum += wordCount
      }
    }
    return hasWordCounts ? sum : nodes.length
  }, [nodes])

  // Toggling `isFullscreen` swaps the outer container between its normal bounded height and
  // a `fixed inset-0` overlay (see the className below) — an abrupt resize `@xyflow/react`
  // doesn't always pick up on its own. `fitView` is called after that resize, but the new
  // container size isn't guaranteed to be reflected in the very next paint (the CSS class
  // swap + browser layout needs a tick to settle), so this is wrapped in a short `setTimeout`
  // rather than called synchronously — cleared on unmount/re-toggle so it never fires stale.
  useEffect(() => {
    const timer = setTimeout(() => {
      fitView({ duration: 200 })
    }, 50)
    return () => clearTimeout(timer)
  }, [isFullscreen, fitView])

  // Escape exits fullscreen — only listens while fullscreen is active.
  useEffect(() => {
    if (!isFullscreen) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setIsFullscreen(false)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isFullscreen])

  return (
    <div
      ref={containerRef}
      className={cn(
        // Context-aware cursor (PHASE-UI-EFFECTS-2.md #10, see index.css) — scoped to this
        // container only via `qn-canvas-cursor`, so it never leaks to the Codex relationship
        // map's separate `<ReactFlow>` instance. `qn-canvas-cursor--connecting` mirrors
        // `connectSourceId` (the same state driving the aria-live announcements and the
        // source-node ring below) so the mouse-visible cursor and the keyboard-visible signal
        // never disagree about whether connect-mode is active.
        'qn-canvas-cursor overflow-hidden border-border',
        connectSourceId && 'qn-canvas-cursor--connecting',
        isFullscreen
          ? 'fixed inset-0 z-50 rounded-none border-0'
          : 'relative mt-4 h-[70vh] min-h-[480px] rounded-2xl border',
      )}
      onKeyDown={handleCanvasKeyDown}
    >
      {/* Connect-mode announcements (docs/06 Phase 9 task 7): visually hidden, but announced
          by screen readers whenever `connectAnnouncement` changes — "Connecting from…",
          "Connected A to B.", "Connection cancelled." The visible cue for sighted keyboard
          users is the ring highlight `displayNodes` applies to the source node below. */}
      <div aria-live="polite" className="sr-only">
        {connectAnnouncement}
      </div>

      <ReactFlow<SceneFlowNode, Edge>
        nodes={displayNodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={handleNodeDragStop}
        onConnect={handleConnect}
        onEdgesDelete={handleEdgesDelete}
        onNodesDelete={handleNodesDelete}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={{ type: 'ink' }}
        fitView
        deleteKeyCode={['Backspace', 'Delete']}
        proOptions={{ hideAttribution: true }}
      >
        <Background className="!bg-background" gap={24} size={1} />
        <Controls
          position="top-right"
          style={{ top: '3.75rem', right: '1rem' }}
          className="!border-none !shadow-none [&>button]:!border-border [&>button]:!bg-card [&>button]:!text-foreground"
        />
        {/* Controls sits below the word-count pill (right-4 top-4) via the top offset above.
            MiniMap has no explicit position — falls back to xyflow's default bottom-right. */}
        <MiniMap
          className="!overflow-hidden !rounded-lg !border !border-border"
          maskColor="oklch(0.2 0 0 / 0.35)"
          pannable
          zoomable
        />
      </ReactFlow>

      {/* Ambient firefly (docs/10 §6, §5) — Night canvas only, and only at delight_level
          'standard'/'playful'. Absent in Day or Calm. Purely decorative chrome over the
          canvas, never over the manuscript surface. */}
      {theme === 'night' && delightLevel !== 'calm' && <Firefly />}

      <div
        className="glass glass-edge pointer-events-none absolute right-4 top-4 z-10 flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-medium text-muted-foreground"
        aria-label="Total words penned on this canvas"
      >
        {motionOk ? <NumberFlow value={totalWords} /> : <span>{totalWords}</span>}
        <span>penned</span>
      </div>

      {/* Top-left corner — clear of the word-count pill and Controls (both right-side) and
          the collapsed Codex toggle (bottom-left), so no collision risk. */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="secondary"
            size="icon-sm"
            className="glass glass-edge pointer-events-auto absolute left-4 top-4 z-10"
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen canvas'}
            onClick={() => setIsFullscreen((v) => !v)}
          >
            {isFullscreen ? <Minimize2 className="size-4" /> : <Maximize className="size-4" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{isFullscreen ? 'Exit fullscreen' : 'Fullscreen canvas'}</TooltipContent>
      </Tooltip>

      {isEmpty && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="glass glass-edge pointer-events-auto flex flex-col items-center gap-1 rounded-2xl px-8 py-10 text-center">
            <LottiePlayer
              animationData={() => import('../../assets/lottie/empty-state.json')}
              loop
              ariaHidden
              className="size-28"
            />
            <p className="text-sm font-medium">Blank canvas — add your first node</p>
            <p className="max-w-xs text-xs text-muted-foreground">
              Scenes, plot points, and loose thoughts all start from the “Add node” button in
              the toolbar.
            </p>
            {/* Canvas templates (docs/06 Phase 9 task 5) — an alternative to building the
                canvas node-by-node. Only ever rendered on a genuinely blank canvas, so the
                backend's 409 (`TemplateAlreadyAppliedError`) is a rare double-click/other-tab
                race rather than the expected path — handled gracefully in
                `useApplyCanvasTemplate`'s `onError` regardless. */}
            <p className="mt-3 text-xs text-muted-foreground">or start from a template</p>
            <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
              {CANVAS_TEMPLATE_MENU.map(({ key, label, icon: Icon }) => {
                const isThisPending =
                  applyTemplate.isPending && applyTemplate.variables?.template_key === key
                return (
                  <Button
                    key={key}
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={applyTemplate.isPending}
                    aria-busy={isThisPending}
                    aria-label={`Start canvas from the ${label} template`}
                    onClick={() => handleApplyTemplate(key)}
                  >
                    <Icon className="size-4" />
                    {isThisPending ? 'Applying…' : label}
                  </Button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <CodexPanel sceneId={selectedNode?.data.sceneId} />

      <NodeEditor
        bookId={bookId}
        bookType={book?.book_type}
        node={selectedNode}
        onClose={() => setSelectedNodeId(null)}
      />
    </div>
  )
}

export type { CanvasNodeData }

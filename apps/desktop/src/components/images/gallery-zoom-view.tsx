import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import gsap from 'gsap'
import { Draggable } from 'gsap/Draggable'
import { InertiaPlugin } from 'gsap/InertiaPlugin'
import { Minus, Plus, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ImageCard } from '@/components/images/image-card'
import { useDelight } from '@/lib/delight'
import type { ImageRead } from '@/lib/api'

gsap.registerPlugin(Draggable, InertiaPlugin)

const MIN_ZOOM = 0.3
const MAX_ZOOM = 1
const DEFAULT_ZOOM = 0.6
const ZOOM_STEP = 0.1
const PAN_STEP = 60

/**
 * PHASE-UI-EFFECTS.md #5 — the freefrontend.com "GSAP draggable/zoom gallery" effect, shipped
 * as an optional view mode on `images-panel.tsx` alongside its plain CSS grid (never a
 * replacement — some users will always prefer the scrollable grid). It renders the exact same
 * `<ImageCard/>` grid inside a GSAP-`Draggable` "stage" the user can pan and zoom (30%–100%),
 * so clicking an image opens the identical `<ImageDetail/>` dialog `image-card.tsx` already
 * wires up for the plain grid — there is no second open-detail code path here.
 *
 * **Delight gating** (`useDelight().motionOk`, same single gate as `wobbly-indicator.tsx`):
 * dragging/panning itself is *never* disabled under Calm/reduced-motion — it's the only way
 * to reach off-screen images in this view, a real navigation mechanism, not decoration. What
 * `motionOk` controls is purely the *feel*: `inertia` (GSAP `InertiaPlugin` momentum/coasting
 * after release) is only enabled when `motionOk`, and zoom tweens use `duration: 0` (an
 * instant jump, no `power2.out` ease) when `!motionOk`. At Calm/reduced-motion, drag is still
 * a real 1:1 pan, it just stops dead the instant the pointer releases instead of coasting.
 *
 * **Keyboard fallback** (not optional — a mouse-only interaction would strand keyboard and
 * screen-reader users): with focus on the viewport (a single `tabIndex={0}` group), arrow
 * keys pan by a fixed step and `+`/`=`/`-`/`_` zoom in/out, entirely independent of pointer
 * drag — `handleKeyDown` never checks `motionOk` or touches inertia, keyboard panning is
 * always a direct `gsap.set` with no momentum regardless of delight level. Keyboard moves
 * write through the same `Draggable` instance (`.update(true)` resyncs its internal x/y
 * bookkeeping after an external `gsap.set` call, per GSAP's documented pattern for
 * externally-driven position changes) so pointer drag and keyboard pan can never fall out of
 * sync with each other or with the recalculated pan bounds.
 *
 * **No instance leaks**: the mount effect below is the only place a `Draggable` is created
 * for this component instance, and its cleanup calls `instance.kill()` (removes all of
 * Draggable's own DOM listeners/refs) plus `gsap.killTweensOf(stage)` (stops any in-flight
 * zoom/reset tween so it can't keep writing to a since-unmounted node). The effect re-runs
 * (kill + recreate) only when `motionOk` flips, which is rare (a mid-session settings change)
 * and cheap — never on every render/frame.
 */
export function GalleryZoomView({
  images,
  bookId,
  readOnly = false,
}: {
  images: ImageRead[]
  bookId?: string
  readOnly?: boolean
}) {
  const { motionOk } = useDelight()
  const viewportRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const draggableRef = useRef<Draggable | null>(null)
  const [zoom, setZoom] = useState(DEFAULT_ZOOM)
  const zoomRef = useRef(zoom)
  zoomRef.current = zoom

  useEffect(() => {
    const stage = stageRef.current
    const viewport = viewportRef.current
    if (!stage || !viewport) return

    // Re-apply whatever zoom level was already dialed in (e.g. this effect re-ran because
    // `motionOk` flipped mid-session) rather than resetting to the default every time.
    gsap.set(stage, { scale: zoomRef.current })

    const [instance] = Draggable.create(stage, {
      type: 'x,y',
      bounds: viewport,
      inertia: motionOk,
      edgeResistance: 0.65,
      dragClickables: false,
    })
    draggableRef.current = instance

    return () => {
      instance.kill()
      gsap.killTweensOf(stage)
      draggableRef.current = null
    }
  }, [motionOk])

  const applyZoom = useCallback(
    (next: number) => {
      const clamped = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(next * 100) / 100))
      setZoom(clamped)
      const stage = stageRef.current
      if (!stage) return
      gsap.to(stage, {
        scale: clamped,
        duration: motionOk ? 0.2 : 0,
        ease: 'power2.out',
        onComplete: () => {
          if (draggableRef.current && viewportRef.current) draggableRef.current.applyBounds(viewportRef.current)
        },
      })
    },
    [motionOk],
  )

  // Direct 1:1 keyboard pan — always momentum-free, regardless of `motionOk`, since this is
  // the accessible fallback and a keyboard user pressing an arrow key expects the view to
  // move exactly once per press, not coast afterward.
  function pan(dx: number, dy: number) {
    const stage = stageRef.current
    const instance = draggableRef.current
    if (!stage || !instance) return
    gsap.set(stage, { x: instance.x + dx, y: instance.y + dy })
    instance.update(true)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    switch (event.key) {
      case 'ArrowUp':
        event.preventDefault()
        pan(0, PAN_STEP)
        break
      case 'ArrowDown':
        event.preventDefault()
        pan(0, -PAN_STEP)
        break
      case 'ArrowLeft':
        event.preventDefault()
        pan(PAN_STEP, 0)
        break
      case 'ArrowRight':
        event.preventDefault()
        pan(-PAN_STEP, 0)
        break
      case '+':
      case '=':
        event.preventDefault()
        applyZoom(zoom + ZOOM_STEP)
        break
      case '-':
      case '_':
        event.preventDefault()
        applyZoom(zoom - ZOOM_STEP)
        break
    }
  }

  function resetView() {
    const stage = stageRef.current
    const instance = draggableRef.current
    if (!stage || !instance) return
    setZoom(DEFAULT_ZOOM)
    gsap.to(stage, {
      x: 0,
      y: 0,
      scale: DEFAULT_ZOOM,
      duration: motionOk ? 0.3 : 0,
      ease: 'power2.out',
      onComplete: () => {
        if (viewportRef.current) instance.applyBounds(viewportRef.current)
      },
    })
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5 self-end">
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label="Zoom out"
          onClick={() => applyZoom(zoom - ZOOM_STEP)}
          disabled={zoom <= MIN_ZOOM}
        >
          <Minus className="size-4" />
        </Button>
        <span className="min-w-10 text-center text-xs text-muted-foreground" aria-live="polite">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label="Zoom in"
          onClick={() => applyZoom(zoom + ZOOM_STEP)}
          disabled={zoom >= MAX_ZOOM}
        >
          <Plus className="size-4" />
        </Button>
        <Button type="button" variant="outline" size="icon-sm" aria-label="Reset pan and zoom" onClick={resetView}>
          <RotateCcw className="size-4" />
        </Button>
      </div>

      <div
        ref={viewportRef}
        role="group"
        aria-label="Draggable, zoomable image gallery — drag to pan, or use arrow keys to pan and the plus/minus keys to zoom"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        className="glass glass-edge relative h-[60vh] overflow-hidden rounded-2xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <div
          ref={stageRef}
          className="grid w-[1400px] grid-cols-5 gap-3 p-4"
          style={{ transformOrigin: '0 0', cursor: 'grab' }}
        >
          {images.map((image) => (
            <ImageCard key={image.id} image={image} bookId={bookId} readOnly={readOnly} />
          ))}
        </div>
      </div>
    </div>
  )
}

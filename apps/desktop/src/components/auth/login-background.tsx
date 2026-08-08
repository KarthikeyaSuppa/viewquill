import { useEffect, useRef, useState } from 'react'

/**
 * Decorative, interactive dot-grid backdrop for `<ProfileGate>` (pre-auth screen, so we
 * cannot read per-profile `delight_level` yet — gate ONLY on the system
 * `prefers-reduced-motion` query, which is available immediately). Reimplements a
 * pointer-pull + click-burst dot-grid effect with plain `requestAnimationFrame` physics —
 * no GSAP, no new dependency.
 *
 * Rendered on a single `<canvas>` (not one DOM node per dot) since a full-viewport grid at
 * a ~30px cell can be a few hundred dots — canvas keeps that to one draw call per frame
 * instead of a few hundred styled elements. Purely decorative: `aria-hidden`, absolutely
 * positioned behind the gate's card, `pointer-events: none` throughout so the profile
 * picker/login form stay fully interactive; pointer/click tracking happens on `window`
 * instead of the canvas itself for exactly that reason.
 *
 * Sizing is driven by a `ResizeObserver` on the wrapper — NOT a one-shot `window.innerWidth`
 * read at mount, which raced layout (embedded preview / StrictMode double-mount) and could
 * lock the canvas at 0×0 with no later resize event to correct it.
 */

const MIN_CELL_SIZE = 32
const MAX_DOTS = 600
const DOT_RADIUS = 1.6
const DOT_OPACITY = 0.35

const PULL_RADIUS = 70
const PULL_EASE = 0.22
const SPRING_K = 0.05
const DAMPING = 0.82
const GRAVITY = 0.22
const BURST_DECAY = 0.045
const BURST_VELOCITY = 6
const BURST_RADIUS = 480
const WAVE_SPEED = 1000 // px/sec — outward stagger speed of the click burst

interface Dot {
  hx: number
  hy: number
  x: number
  y: number
  vx: number
  vy: number
  burstEnergy: number
  burstActivateAt: number | null
  burstDirX: number
  burstDirY: number
  burstStrength: number
}

function buildGrid(width: number, height: number): Dot[] {
  let cell = MIN_CELL_SIZE
  let cols = Math.floor(width / cell) + 1
  let rows = Math.floor(height / cell) + 1
  // Thin the grid on very large viewports rather than exceeding the dot-count cap.
  while (cols * rows > MAX_DOTS && cell < 200) {
    cell += 2
    cols = Math.floor(width / cell) + 1
    rows = Math.floor(height / cell) + 1
  }

  const offsetX = (width - (cols - 1) * cell) / 2
  const offsetY = (height - (rows - 1) * cell) / 2

  const dots: Dot[] = []
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const hx = offsetX + col * cell
      const hy = offsetY + row * cell
      dots.push({
        hx,
        hy,
        x: hx,
        y: hy,
        vx: 0,
        vy: 0,
        burstEnergy: 0,
        burstActivateAt: null,
        burstDirX: 0,
        burstDirY: 0,
        burstStrength: 0,
      })
    }
  }
  return dots
}

/** True while the OS-level reduced-motion preference is on; tracks live changes to it. */
function useSystemReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return reduced
}

export function LoginBackground() {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const reducedMotion = useSystemReducedMotion()

  useEffect(() => {
    const canvas = canvasRef.current
    const wrapper = wrapperRef.current
    if (!canvas || !wrapper) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let width = 0
    let height = 0
    let dots: Dot[] = []

    // Resolve the dot color from a theme token once per resize/mount so it always matches
    // the active theme — low opacity is applied via `globalAlpha`, not baked into the color
    // string, so it reads correctly regardless of the token's color format (oklch etc.).
    function dotColor(): string {
      const raw = getComputedStyle(document.documentElement).getPropertyValue('--muted-foreground').trim()
      return raw || 'currentColor'
    }

    // Size from the wrapper's real laid-out box (see file header) — the ResizeObserver below
    // calls this once layout exists and again on any change.
    function resize() {
      width = wrapper!.clientWidth
      height = wrapper!.clientHeight
      if (width === 0 || height === 0) return
      const dpr = window.devicePixelRatio || 1
      canvas!.width = Math.round(width * dpr)
      canvas!.height = Math.round(height * dpr)
      canvas!.style.width = `${width}px`
      canvas!.style.height = `${height}px`
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
      dots = buildGrid(width, height)
    }

    function drawStatic() {
      if (width === 0 || height === 0) return
      ctx!.clearRect(0, 0, width, height)
      ctx!.globalAlpha = DOT_OPACITY
      ctx!.fillStyle = dotColor()
      for (const dot of dots) {
        ctx!.beginPath()
        ctx!.arc(dot.hx, dot.hy, DOT_RADIUS, 0, Math.PI * 2)
        ctx!.fill()
      }
      ctx!.globalAlpha = 1
    }

    if (reducedMotion) {
      // Static frozen grid: draw once on (re)size, no pointer listeners, no RAF loop.
      const ro = new ResizeObserver(() => {
        resize()
        drawStatic()
      })
      ro.observe(wrapper)
      // Belt-and-suspenders: some embedded/iframe hosts finish layout a frame after mount
      // without a ResizeObserver change event the observer catches — redraw next frame too.
      const raf = requestAnimationFrame(() => {
        resize()
        drawStatic()
      })
      return () => {
        ro.disconnect()
        cancelAnimationFrame(raf)
      }
    }

    // ── Interactive path (pointer-pull + click-burst physics) ────────────────────────
    const pointer = { x: -9999, y: -9999, active: false }
    let rafId = 0
    let lastTime = performance.now()

    function onPointerMove(e: PointerEvent) {
      pointer.x = e.clientX
      pointer.y = e.clientY
      pointer.active = true
    }

    function onBurst(e: PointerEvent | MouseEvent) {
      const cx = e.clientX
      const cy = e.clientY
      const now = performance.now()
      for (const dot of dots) {
        const dx = dot.hx - cx
        const dy = dot.hy - cy
        const dist = Math.hypot(dx, dy)
        if (dist > BURST_RADIUS) continue
        const strength = 1 - dist / BURST_RADIUS
        const delayMs = (dist / WAVE_SPEED) * 1000
        dot.burstActivateAt = now + delayMs
        dot.burstStrength = strength
        // Push outward along the home→click vector; guard the degenerate zero-distance case.
        if (dist > 0.01) {
          dot.burstDirX = dx / dist
          dot.burstDirY = dy / dist
        } else {
          dot.burstDirX = 0
          dot.burstDirY = -1
        }
      }
    }

    function tick(now: number) {
      // Self-heal sizing: if the wrapper's laid-out box differs from what we sized to (it can
      // be 0 at mount in an embedded/iframe host and get its real box a frame later, with no
      // ResizeObserver change the observer catches), resize now. One cheap read per frame;
      // `resize()` only rebuilds the grid when the size actually changed.
      if (wrapper!.clientWidth !== width || wrapper!.clientHeight !== height) resize()

      const dtMs = Math.min(now - lastTime, 48) // clamp so a tab-switch stall doesn't explode
      lastTime = now
      const timeScale = dtMs / (1000 / 60)
      const frameDamping = Math.pow(DAMPING, timeScale)

      ctx!.clearRect(0, 0, width, height)
      ctx!.globalAlpha = DOT_OPACITY
      ctx!.fillStyle = dotColor()
      ctx!.beginPath()

      for (const dot of dots) {
        if (dot.burstActivateAt !== null && now >= dot.burstActivateAt) {
          const magnitude = BURST_VELOCITY * dot.burstStrength
          dot.vx += dot.burstDirX * magnitude
          dot.vy += dot.burstDirY * magnitude
          dot.burstEnergy = 1
          dot.burstActivateAt = null
        }

        // Pointer-pull: ease toward the cursor, proportional to closeness, within radius.
        const dx = pointer.x - dot.x
        const dy = pointer.y - dot.y
        const dist = Math.hypot(dx, dy)
        if (pointer.active && dist < PULL_RADIUS && dist > 0.01) {
          const pull = (1 - dist / PULL_RADIUS) * PULL_EASE * timeScale
          dot.vx += dx * pull
          dot.vy += dy * pull
        }

        // Click burst: gravity acts only while the dot still has burst energy, then decays.
        if (dot.burstEnergy > 0) {
          dot.vy += GRAVITY * dot.burstEnergy * timeScale
          dot.burstEnergy = Math.max(0, dot.burstEnergy - BURST_DECAY * timeScale)
        }

        // Elastic spring back to the dot's home position — always active, so it both
        // recovers from a pointer pull once the cursor moves away and settles a burst.
        dot.vx += (dot.hx - dot.x) * SPRING_K * timeScale
        dot.vy += (dot.hy - dot.y) * SPRING_K * timeScale

        dot.vx *= frameDamping
        dot.vy *= frameDamping
        dot.x += dot.vx * timeScale
        dot.y += dot.vy * timeScale

        const rx = Math.round(dot.x * 10) / 10
        const ry = Math.round(dot.y * 10) / 10
        ctx!.moveTo(rx + DOT_RADIUS, ry)
        ctx!.arc(rx, ry, DOT_RADIUS, 0, Math.PI * 2)
      }

      ctx!.fill()
      ctx!.globalAlpha = 1
      rafId = requestAnimationFrame(tick)
    }

    const ro = new ResizeObserver(() => resize())
    ro.observe(wrapper)
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('pointerup', onBurst, { passive: true })
    rafId = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(rafId)
      ro.disconnect()
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onBurst)
    }
  }, [reducedMotion])

  return (
    <div
      ref={wrapperRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
    >
      <canvas ref={canvasRef} className="block h-full w-full" />
    </div>
  )
}

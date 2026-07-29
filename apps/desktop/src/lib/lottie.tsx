import { useEffect, useState } from 'react'
import { useLottie } from 'lottie-react'
import { useDelight } from '@/lib/delight'

/**
 * The single wrapper every Lottie usage in this app must go through — centralizes
 * delight-level/reduced-motion gating (`useDelight().motionOk`) so no consumer has to
 * re-implement it. At Calm level or under `prefers-reduced-motion`, the animation is
 * rendered frozen on its first frame (never unmounted, so layout never shifts); otherwise
 * it autoplays and loops per the `loop` prop.
 *
 * Usage: `<LottiePlayer animationData={() => import('@/assets/lottie/firefly-idle.json')} />`
 * (or pass the parsed JSON object directly — both are supported).
 */

type LottieJson = Record<string, unknown>
type LottieLoader = () => Promise<{ default: LottieJson } | LottieJson>
type LottieSource = LottieJson | LottieLoader

export interface LottiePlayerProps {
  animationData: LottieSource
  /** Defaults to true. Ignored (forced off) when `motionOk` is false. */
  loop?: boolean
  className?: string
  style?: React.CSSProperties
  /** Defaults to true — these are decorative, not content. */
  ariaHidden?: boolean
}

function isLoader(source: LottieSource): source is LottieLoader {
  return typeof source === 'function'
}

function useResolvedAnimationData(source: LottieSource): LottieJson | null {
  const [resolved, setResolved] = useState<LottieJson | null>(isLoader(source) ? null : source)

  useEffect(() => {
    if (!isLoader(source)) {
      setResolved(source)
      return
    }
    let cancelled = false
    void source().then((mod) => {
      if (cancelled) return
      const hasDefault = (m: { default: LottieJson } | LottieJson): m is { default: LottieJson } => 'default' in m
      const data: LottieJson = hasDefault(mod) ? mod.default : mod
      setResolved(data)
    })
    return () => {
      cancelled = true
    }
  }, [source])

  return resolved
}

export function LottiePlayer({ animationData, loop = true, className, style, ariaHidden = true }: LottiePlayerProps) {
  const { motionOk } = useDelight()
  const resolvedData = useResolvedAnimationData(animationData)

  const { View, play, goToAndStop, animationLoaded } = useLottie({
    animationData: resolvedData ?? {},
    loop: motionOk && loop,
    autoplay: motionOk,
    className,
    style,
  })

  useEffect(() => {
    if (!animationLoaded) return
    if (motionOk) {
      play()
    } else {
      // Freeze on the first frame — never unmount, never autoplay/loop.
      goToAndStop(0, true)
    }
  }, [motionOk, animationLoaded, play, goToAndStop])

  if (!resolvedData) return null

  return <div aria-hidden={ariaHidden}>{View}</div>
}

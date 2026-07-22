import { motion } from 'motion/react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ThemeToggle } from '@/components/theme-toggle'
import { Firefly } from '@/components/firefly'
import { useHealth } from '@/queries/health'
import { cn } from '@/lib/utils'

function StatusDot({ className }: { className?: string }) {
  return <span className={cn('size-2 shrink-0 rounded-full', className)} />
}

/** The Phase 0 boot/status screen: wordmark, sidecar + local-AI status, day/night toggle. */
export function StatusScreen() {
  const { data: health, isLoading, isError } = useHealth()

  const sidecar = isLoading
    ? { dot: 'bg-amber-500', label: 'Connecting…' }
    : isError
      ? { dot: 'bg-red-500', label: 'Sidecar offline' }
      : { dot: 'bg-emerald-500', label: 'Sidecar online' }

  const ollamaReachable = health?.ollama.reachable ?? false

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 z-0"
        style={{
          background:
            'radial-gradient(60% 50% at 50% 40%, oklch(0.54 0.21 277 / 0.16), transparent 70%)',
        }}
      />

      <Firefly />

      <ThemeToggle className="fixed top-6 right-6 z-10" />

      <motion.div
        initial={{ opacity: 0, scale: 0.96, filter: 'blur(8px)' }}
        animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className="relative z-10 w-full max-w-[420px] px-4"
      >
        <Card className="glass glass-edge rounded-2xl border-0 py-8 shadow-none">
          <CardHeader className="items-center text-center">
            <h1 className="text-3xl font-semibold tracking-tight">Quillnight</h1>
            <p className="text-sm text-muted-foreground">Your night studio for stories.</p>
          </CardHeader>

          <CardContent className="flex flex-col gap-4">
            <Separator />

            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Sidecar</span>
              <span className="flex items-center gap-2 font-medium">
                <StatusDot className={sidecar.dot} />
                {sidecar.label}
              </span>
            </div>

            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Local AI</span>
              {ollamaReachable ? (
                <Badge className="bg-emerald-500 text-white">Local AI ready</Badge>
              ) : (
                <Badge variant="secondary" className="text-muted-foreground">
                  Local AI: not running
                </Badge>
              )}
            </div>

            {health?.version ? (
              <p className="text-center text-xs text-muted-foreground">v{health.version}</p>
            ) : null}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

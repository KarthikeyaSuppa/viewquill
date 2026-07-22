import { AnimatePresence, motion } from 'motion/react'
import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useThemeStore } from '@/stores/theme'
import { cn } from '@/lib/utils'

/** Fixed top-right Day/Night toggle — a glass pill housing a crossfading Sun/Moon icon. */
export function ThemeToggle({ className }: { className?: string }) {
  const theme = useThemeStore((s) => s.theme)
  const toggle = useThemeStore((s) => s.toggle)

  return (
    <div className={cn('glass rounded-full p-1', className)}>
      <Button
        variant="ghost"
        size="icon"
        onClick={toggle}
        aria-label={theme === 'night' ? 'Switch to day theme' : 'Switch to night theme'}
        className="relative overflow-hidden rounded-full"
      >
        <AnimatePresence mode="wait" initial={false}>
          {theme === 'night' ? (
            <motion.span
              key="moon"
              initial={{ opacity: 0, scale: 0.6, filter: 'blur(4px)' }}
              animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, scale: 0.6, filter: 'blur(4px)' }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="flex items-center justify-center"
            >
              <Moon className="size-4" />
            </motion.span>
          ) : (
            <motion.span
              key="sun"
              initial={{ opacity: 0, scale: 0.6, filter: 'blur(4px)' }}
              animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, scale: 0.6, filter: 'blur(4px)' }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="flex items-center justify-center"
            >
              <Sun className="size-4" />
            </motion.span>
          )}
        </AnimatePresence>
      </Button>
    </div>
  )
}

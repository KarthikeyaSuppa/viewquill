import { useState } from 'react'
import { motion } from 'motion/react'
import { ArrowLeft, Plus } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ThemeToggle } from '@/components/theme-toggle'
import { Firefly } from '@/components/firefly'
import { LoginBackground } from '@/components/auth/login-background'
import { AVATAR_OPTIONS, resolveAvatar } from '@/components/auth/avatars'
import { useCreateProfile, useLogin, useProfiles } from '@/queries/profiles'
import type { Profile } from '@/lib/api'
import { cn } from '@/lib/utils'

type View = { step: 'picker' } | { step: 'login'; profile: Profile } | { step: 'create' }

function AvatarBadge({ avatarId, className }: { avatarId: string | null | undefined; className?: string }) {
  const avatar = resolveAvatar(avatarId)
  return (
    <span
      className={cn(
        'flex size-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-2xl ring-1 ring-primary/20',
        className,
      )}
      role="img"
      aria-label={avatar.label}
    >
      {avatar.emoji}
    </span>
  )
}

/** Picker of existing profiles + an "Add profile" tile (only while under the 2-profile cap). */
function PickerView({ onPick, onAdd }: { onPick: (p: Profile) => void; onAdd: () => void }) {
  const { data: profiles, isLoading } = useProfiles()

  if (isLoading) {
    return (
      <div className="space-y-2.5">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    )
  }

  const list = profiles ?? []
  const canAdd = list.length < 2

  if (list.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-4 text-center">
        <p className="text-sm text-muted-foreground">Create your profile to begin.</p>
        <Button onClick={onAdd}>
          <Plus /> Create your profile
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      {list.map((profile) => (
        <button
          key={profile.id}
          type="button"
          onClick={() => onPick(profile)}
          className="flex w-full items-center gap-3 rounded-xl border border-border p-3 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <AvatarBadge avatarId={profile.avatar} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{profile.display_name || profile.username}</p>
            <p className="truncate text-xs text-muted-foreground">@{profile.username}</p>
          </div>
        </button>
      ))}

      {canAdd && (
        <button
          type="button"
          onClick={onAdd}
          className="flex w-full items-center gap-3 rounded-xl border border-dashed border-border p-3 text-left text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="flex size-12 shrink-0 items-center justify-center rounded-full border border-dashed border-border">
            <Plus className="size-4" />
          </span>
          <span className="text-sm font-medium">Add profile</span>
        </button>
      )}
    </div>
  )
}

/** Password login for one preselected profile. */
function LoginView({ profile, onBack }: { profile: Profile; onBack: () => void }) {
  const [password, setPassword] = useState('')
  const login = useLogin()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    login.mutate({ username: profile.username, password })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-center gap-3">
        <AvatarBadge avatarId={profile.avatar} />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{profile.display_name || profile.username}</p>
          <p className="truncate text-xs text-muted-foreground">@{profile.username}</p>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="login-password">Password</Label>
        <Input
          id="login-password"
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      </div>

      <div className="flex items-center justify-between pt-1">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft /> Back
        </Button>
        <Button type="submit" size="sm" disabled={login.isPending || password.length === 0}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </Button>
      </div>
    </form>
  )
}

/** Create a new profile, then auto-login with the same credentials. */
function CreateView({ onBack }: { onBack: () => void }) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [avatarId, setAvatarId] = useState(AVATAR_OPTIONS[0].id)

  const createProfile = useCreateProfile()
  const login = useLogin()

  const isBusy = createProfile.isPending || login.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    createProfile.mutate(
      {
        username,
        password,
        display_name: displayName.trim() || undefined,
        avatar: avatarId,
      },
      {
        onSuccess: () => {
          login.mutate({ username, password })
        },
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="create-username">Username</Label>
        <Input
          id="create-username"
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="create-display-name">Display name (optional)</Label>
        <Input
          id="create-display-name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="create-password">Password</Label>
        <Input
          id="create-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          required
        />
      </div>

      <div className="space-y-1.5">
        <Label>Avatar</Label>
        <div className="flex flex-wrap gap-2">
          {AVATAR_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setAvatarId(option.id)}
              aria-pressed={avatarId === option.id}
              aria-label={option.label}
              className={cn(
                'flex size-10 items-center justify-center rounded-full bg-primary/10 text-xl ring-1 ring-primary/20 transition-transform hover:scale-105',
                avatarId === option.id && 'ring-2 ring-primary',
              )}
            >
              {option.emoji}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between pt-1">
        <Button type="button" variant="ghost" size="sm" onClick={onBack} disabled={isBusy}>
          <ArrowLeft /> Back
        </Button>
        <Button type="submit" size="sm" disabled={isBusy || username.trim().length === 0 || password.length === 0}>
          {isBusy ? 'Creating…' : 'Create profile'}
        </Button>
      </div>
    </form>
  )
}

/**
 * The profile picker / create / login gate (UI/profile LOCK — not encryption; the password
 * gates who's at the keyboard locally, it never encrypts data). Shown by `BootGate` once the
 * sidecar is healthy but no session token is present yet.
 */
export function ProfileGate() {
  const [view, setView] = useState<View>({ step: 'picker' })

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background">
      <LoginBackground />

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
            <CardTitle className="text-3xl font-semibold tracking-tight">Quillnight</CardTitle>
            <CardDescription>
              {view.step === 'create'
                ? 'Create your profile to begin.'
                : view.step === 'login'
                  ? 'Enter your password to continue.'
                  : 'Who is writing tonight?'}
            </CardDescription>
          </CardHeader>

          <CardContent>
            {view.step === 'picker' && (
              <PickerView
                onPick={(profile) => setView({ step: 'login', profile })}
                onAdd={() => setView({ step: 'create' })}
              />
            )}
            {view.step === 'login' && (
              <LoginView profile={view.profile} onBack={() => setView({ step: 'picker' })} />
            )}
            {view.step === 'create' && <CreateView onBack={() => setView({ step: 'picker' })} />}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}

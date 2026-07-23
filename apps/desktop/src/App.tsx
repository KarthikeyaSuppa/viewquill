import { RouterProvider } from 'react-router-dom'
import { Providers } from '@/components/providers'
import { StatusScreen } from '@/components/status-screen'
import { ProfileGate } from '@/components/auth/profile-gate'
import { useHealth } from '@/queries/health'
import { useAuthStore } from '@/stores/auth'
import { router } from '@/router'

/**
 * Gates the router behind sidecar health, then behind a local profile session: boot
 * screen until the sidecar is reachable, the profile picker/login until a session
 * token exists (memory-only — see stores/auth.ts), then the routed app.
 */
function BootGate() {
  const { isLoading, isError } = useHealth()
  const token = useAuthStore((s) => s.token)

  if (isLoading || isError) {
    return <StatusScreen />
  }

  if (!token) {
    return <ProfileGate />
  }

  return <RouterProvider router={router} />
}

export default function App() {
  return (
    <Providers>
      <BootGate />
    </Providers>
  )
}

import { RouterProvider } from 'react-router-dom'
import { Providers } from '@/components/providers'
import { StatusScreen } from '@/components/status-screen'
import { useHealth } from '@/queries/health'
import { router } from '@/router'

/** Gates the router behind sidecar health: shows the boot screen until it's reachable. */
function BootGate() {
  const { isLoading, isError } = useHealth()

  if (isLoading || isError) {
    return <StatusScreen />
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

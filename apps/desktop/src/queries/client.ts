import { QueryClient } from '@tanstack/react-query'

/** Shared React Query client for the sidecar API (docs/02). */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 1000 * 30,
    },
  },
})
